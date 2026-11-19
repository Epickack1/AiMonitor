"""Тесты форм: фильтр истории, создание и изменение проверки,
отмена отслеживания модели и загрузка логотипа разработчика.

Для модуля создаётся тестовая база Django с двумя моделями и тремя
проверками. Загруженные файлы сохраняются во временный каталог.
"""

import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.test.utils import setup_databases, teardown_databases
from django.utils import timezone
from PIL import Image

import watchlist.validators
from checks.forms import CheckFilterForm, CheckForm
from checks.models import Check
from watchlist.models import AIModel, Vendor

AVAILABLE = Check.Status.AVAILABLE


def moscow(*args):
    return timezone.make_aware(datetime.datetime(*args))


@pytest.fixture(scope="module")
def data():
    old_config = setup_databases(verbosity=0, interactive=False)
    openai = Vendor.objects.create(slug="openai", name="OpenAI")
    google = Vendor.objects.create(slug="google", name="Google")
    gpt = AIModel.objects.create(
        openrouter_id="openai/gpt-4o-mini", name="OpenAI: GPT-4o-mini",
        vendor=openai,
    )
    gemma = AIModel.objects.create(
        openrouter_id="google/gemma:free", name="Google: Gemma (free)",
        vendor=google,
    )
    Check.objects.create(model=gpt, status=AVAILABLE, uptime=99.0,
                         checked_at=moscow(2026, 9, 26, 10, 0))
    Check.objects.create(model=gpt, status=AVAILABLE, uptime=100.0,
                         checked_at=moscow(2026, 9, 27, 11, 0))
    Check.objects.create(model=gemma, status=Check.Status.NOT_FOUND,
                         checked_at=moscow(2026, 9, 26, 10, 0))
    yield {"gpt": gpt, "gemma": gemma}
    teardown_databases(old_config, verbosity=0)


def check_data(model, **changes):
    values = {
        "model": model.pk,
        "checked_at": "2026-09-28T12:00",
        "status": AVAILABLE,
        "uptime": "98.5",
    }
    values.update(changes)
    return values


def png(size=(8, 8)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format="PNG")
    return SimpleUploadedFile("logo.png", buffer.getvalue(),
                              content_type="image/png")


# --- Фильтр истории (forms.Form) ---

def test_filter_form_converts_values(data):
    form = CheckFilterForm(
        {"day": "2026-09-26", "status": AVAILABLE, "vendor": "openai"}
    )
    assert form.is_valid()
    assert form.cleaned_data["day"] == datetime.date(2026, 9, 26)
    assert form.cleaned_data["vendor"].name == "OpenAI"


def test_filter_form_rejects_wrong_values(data):
    form = CheckFilterForm(
        {"day": "26.13.2026", "status": "broken", "vendor": "nobody"}
    )
    assert not form.is_valid()
    assert set(form.errors) == {"day", "status", "vendor"}
    assert "day" not in form.cleaned_data


def test_filter_from_address_bar(data):
    response = Client().get("/checks/?vendor=google")
    assert response.context["page"].paginator.count == 1
    response = Client().get("/checks/?vendor=google&day=2026-09-27")
    assert response.context["page"].paginator.count == 0


def test_filter_errors_shown_without_traceback(data):
    response = Client().get("/checks/?day=abc")
    assert response.status_code == 200
    text = response.content.decode()
    assert "Введите правильную дату" in text
    assert response.context["page"].paginator.count == 3


# --- Проверка (ModelForm) ---

def test_check_form_fields_and_widgets(data):
    form = CheckForm()
    assert list(form.fields) == ["model", "checked_at", "status", "uptime"]
    assert form.fields["uptime"].label == "Аптайм, %"
    assert 'class="form-control"' in str(form["uptime"])
    assert 'type="datetime-local"' in str(form["checked_at"])
    assert form.fields["model"].required
    assert not form.fields["uptime"].required


def test_create_page_get(data):
    response = Client().get(f"/checks/new/?model={data['gpt'].pk}")
    assert response.status_code == 200
    assert response.context["form"].initial["model"] == str(data["gpt"].pk)
    assert "csrfmiddlewaretoken" in response.content.decode()


def test_create_check(data):
    before = Check.objects.count()
    response = Client().post("/checks/new/", check_data(data["gpt"]))
    assert response.status_code == 302
    check = Check.objects.latest("id")
    assert response["Location"] == f"/checks/{check.pk}/"
    assert Check.objects.count() == before + 1
    assert (check.model, check.status, check.uptime) == (
        data["gpt"], AVAILABLE, 98.5
    )
    assert timezone.localtime(check.checked_at).hour == 12
    check.delete()


def test_create_check_with_errors_keeps_values(data):
    before = Check.objects.count()
    response = Client().post("/checks/new/", check_data(
        data["gpt"], checked_at="2099-01-01T10:00", uptime="150"
    ))
    assert response.status_code == 200
    errors = response.context["form"].errors
    assert "будущем" in errors["checked_at"][0]
    assert "100" in errors["uptime"][0]
    assert 'value="150"' in response.content.decode()
    assert Check.objects.count() == before


def test_not_found_without_uptime(data):
    form = CheckForm(check_data(data["gemma"],
                                status=Check.Status.NOT_FOUND, uptime="10"))
    assert not form.is_valid()
    assert "аптайма быть не может" in form.errors["uptime"][0]


def test_duplicate_check_is_rejected(data):
    response = Client().post("/checks/new/", check_data(
        data["gpt"], checked_at="2026-09-26T10:00"
    ))
    assert response.status_code == 200
    errors = response.context["form"].non_field_errors()
    assert "уже есть проверка на это время" in errors[0]
    assert "alert-danger" in response.content.decode()


def test_same_time_other_model_allowed(data):
    form = CheckForm(check_data(data["gemma"], checked_at="2026-09-27T11:00",
                                status=Check.Status.DOWN, uptime=""))
    assert form.is_valid(), form.errors


def test_untracked_model_not_offered_for_new_check(data):
    data["gemma"].untrack()
    try:
        assert data["gemma"] not in CheckForm().fields["model"].queryset
        check = Check.objects.get(model=data["gemma"])
        edit_form = CheckForm(instance=check)
        assert data["gemma"] in edit_form.fields["model"].queryset
    finally:
        data["gemma"].track()


def test_edit_check(data):
    check = Check.objects.get(model=data["gpt"], uptime=99.0)
    before = Check.objects.count()
    page = Client().get(f"/checks/{check.pk}/edit/")
    assert 'value="2026-09-26T10:00"' in page.content.decode()
    # Сохранение без изменений: проверка не конфликтует сама с собой
    response = Client().post(f"/checks/{check.pk}/edit/", check_data(
        data["gpt"], checked_at="2026-09-26T10:00", uptime="99"
    ))
    assert response.status_code == 302
    response = Client().post(f"/checks/{check.pk}/edit/", check_data(
        data["gpt"], checked_at="2026-09-26T10:00", uptime="97.5"
    ))
    check.refresh_from_db()
    assert check.uptime == 97.5
    assert Check.objects.count() == before


def test_edit_into_conflict_is_rejected(data):
    check = Check.objects.get(model=data["gpt"], uptime=100.0)
    response = Client().post(f"/checks/{check.pk}/edit/", check_data(
        data["gpt"], checked_at="2026-09-26T10:00"
    ))
    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    check.refresh_from_db()
    assert timezone.localtime(check.checked_at).day == 27


def test_missing_check_returns_404(data):
    assert Client().get("/checks/99999/").status_code == 404
    assert Client().get("/checks/99999/edit/").status_code == 404


# --- Отмена отслеживания (POST и CSRF) ---

def test_untrack_by_post(data):
    gpt = data["gpt"]
    response = Client().post(f"/models/{gpt.openrouter_id}/untrack/")
    assert response.status_code == 302
    gpt.refresh_from_db()
    assert not gpt.is_tracked
    assert gpt.checks.count() == 2              # запись и история на месте
    Client().post(f"/models/{gpt.openrouter_id}/track/")
    gpt.refresh_from_db()
    assert gpt.is_tracked


def test_untrack_by_get_is_not_allowed(data):
    gpt = data["gpt"]
    response = Client().get(f"/models/{gpt.openrouter_id}/untrack/")
    assert response.status_code == 405
    gpt.refresh_from_db()
    assert gpt.is_tracked


def test_post_without_csrf_token_is_rejected(data):
    client = Client(enforce_csrf_checks=True)
    response = client.post(f"/models/{data['gpt'].openrouter_id}/untrack/")
    assert response.status_code == 403
    response = client.post("/checks/new/", check_data(data["gpt"]))
    assert response.status_code == 403


def test_model_page_has_post_form(data):
    text = Client().get("/models/openai/gpt-4o-mini/").content.decode()
    assert 'action="/models/openai/gpt-4o-mini/untrack/"' in text
    assert "csrfmiddlewaretoken" in text


# --- Загрузка логотипа (ImageField) ---

def test_logo_upload(data, tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        page = Client().get("/vendors/openai/logo/")
        assert 'enctype="multipart/form-data"' in page.content.decode()
        response = Client().post("/vendors/openai/logo/", {"logo": png()})
        assert response.status_code == 302
        vendor = Vendor.objects.get(slug="openai")
        assert vendor.logo.name.startswith("vendors/logo")
        assert (tmp_path / vendor.logo.name).exists()
        text = Client().get("/vendors/openai/").content.decode()
        assert f'src="/media/{vendor.logo.name}"' in text


def test_logo_must_be_image(data, tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        fake = SimpleUploadedFile("logo.png", b"not an image",
                                  content_type="image/png")
        response = Client().post("/vendors/google/logo/", {"logo": fake})
    assert response.status_code == 200
    assert response.context["form"].errors["logo"]
    assert not Vendor.objects.get(slug="google").logo


def test_logo_size_limit(data, tmp_path, monkeypatch):
    monkeypatch.setattr(watchlist.validators, "MAX_LOGO_SIZE", 10)
    with override_settings(MEDIA_ROOT=tmp_path):
        response = Client().post("/vendors/google/logo/", {"logo": png()})
    assert "больше 2 МБ" in response.context["form"].errors["logo"][0]


def test_missing_vendor_logo_page(data):
    assert Client().get("/vendors/nobody/logo/").status_code == 404
