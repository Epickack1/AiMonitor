"""Тесты Django-моделей, переноса данных и ORM-запросов истории проверок.

Для модуля создаётся тестовая база Django (в памяти) и заполняется
командой import_json из тестовых JSON-файлов, поэтому тесты
не зависят от данных проекта.
"""

import pytest
from django.core.exceptions import FieldError
from django.db import connection
from django.db.models import ProtectedError
from django.test import Client
from django.test.utils import (
    CaptureQueriesContext,
    setup_databases,
    teardown_databases,
)

import checks.views
from checks.management.commands.import_json import import_data
from checks.management.commands.import_pr7 import import_pr7
from checks.models import Check
from db.import_json import main as import_json_to_sqlite
from models import AIModel as Model
from models import CheckResult
from models.provider import STATUS_AVAILABLE, STATUS_NOT_FOUND
from storage import save_history, save_watchlist
from watchlist.models import AIModel, Vendor


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    """Тестовая база Django с тремя моделями и пятью проверками."""
    old_config = setup_databases(verbosity=0, interactive=False)
    gpt = Model("openai/gpt-4o-mini", "OpenAI: GPT-4o-mini")
    gemma = Model("google/gemma:free", "Google: Gemma (free)")
    removed = Model("old/model", "old/model")
    folder = tmp_path_factory.mktemp("json")
    save_watchlist([gpt, gemma], folder / "watchlist.json")
    save_history(
        [
            CheckResult(removed, STATUS_AVAILABLE, 90.0, "2026-09-25 09:00"),
            CheckResult(gpt, STATUS_AVAILABLE, 99.0, "2026-09-26 10:00"),
            CheckResult(gemma, STATUS_NOT_FOUND, None, "2026-09-26 10:00"),
            CheckResult(gpt, STATUS_AVAILABLE, 100.0, "2026-09-27 11:00"),
            CheckResult(gemma, STATUS_AVAILABLE, None, "2026-09-27 11:00"),
        ],
        folder / "history.json",
    )
    counts = import_data(folder / "watchlist.json", folder / "history.json")
    yield folder, counts
    teardown_databases(old_config, verbosity=0)


def page(url):
    response = Client().get(url)
    assert response.status_code == 200
    return response


def names(response):
    return [check.model.openrouter_id for check in response.context["page"]]


def test_import_json(data):
    folder, counts = data
    assert counts == (3, 5)
    assert Check.objects.count() == 5
    removed = AIModel.objects.get(openrouter_id="old/model")
    assert not removed.is_tracked
    assert removed.vendor.slug == "old"


def test_import_json_can_be_repeated(data):
    folder, _ = data
    assert import_data(
        folder / "watchlist.json", folder / "history.json"
    ) == (3, 5)
    assert AIModel.objects.count() == 3


def test_reverse_relations(data):
    gpt = AIModel.objects.get(openrouter_id="openai/gpt-4o-mini")
    assert gpt.checks.count() == 2
    assert gpt.vendor.models.get() == gpt
    assert gpt.is_free is False
    assert AIModel.objects.get(openrouter_id="google/gemma:free").is_free


def test_vendor_with_models_is_protected(data):
    with pytest.raises(ProtectedError):
        Vendor.objects.get(slug="openai").delete()


def test_filter_by_related_field(data):
    assert Check.objects.filter(model__vendor__name="Google").count() == 2
    assert Check.objects.filter(model__name__icontains="gpt").count() == 2
    gpt = AIModel.objects.get(openrouter_id="openai/gpt-4o-mini")
    assert Check.objects.filter(model=gpt).count() == 2
    assert Check.objects.filter(model_id=gpt.id).count() == 2


def test_wrong_field_path(data):
    with pytest.raises(FieldError):
        Check.objects.filter(name="x").count()


def test_history_loads_related_models_in_one_query(data):
    with CaptureQueriesContext(connection) as queries:
        found, _, _ = checks.views.filter_checks({})
        vendors = [check.model.vendor.name for check in found]
    assert len(vendors) == 5
    assert len(queries) == 1


def test_history_without_filters(data):
    response = page("/checks/")
    assert response.context["page"].paginator.count == 5
    assert response.context["errors"] == []
    assert "checks/history.html" in [t.name for t in response.templates]


def test_history_several_filters(data):
    response = page("/checks/?day=2026-09-26")
    assert response.context["page"].paginator.count == 2
    response = page(
        f"/checks/?day=2026-09-27&status={STATUS_AVAILABLE}&vendor=google"
    )
    assert names(response) == ["google/gemma:free"]


def test_history_search_by_model(data):
    response = page("/checks/?q=GEMMA")
    assert names(response) == ["google/gemma:free", "google/gemma:free"]


def test_history_invalid_date(data):
    response = page(f"/checks/?day=2026-13-45&status={STATUS_AVAILABLE}")
    assert len(response.context["errors"]) == 1
    assert "Некорректная дата" in response.content.decode()
    assert response.context["page"].paginator.count == 4


def test_history_invalid_status(data):
    response = page("/checks/?status=Ошибка")
    assert "Неизвестный статус" in response.context["errors"][0]
    assert response.context["page"].paginator.count == 5


def test_history_sort(data):
    new = [check.checked_at for check in page("/checks/").context["page"]]
    old = [check.checked_at
           for check in page("/checks/?sort=old").context["page"]]
    assert new == sorted(new, reverse=True)
    assert old == sorted(old)


def test_history_sort_uptime_nulls_last(data):
    response = page("/checks/?sort=uptime")
    uptimes = [check.uptime for check in response.context["page"]]
    assert uptimes == [100.0, 99.0, 90.0, None, None]


def test_history_unknown_sort_ignored(data):
    assert page("/checks/?sort=hack").context["sort"] == "new"


def test_history_days_and_statuses(data):
    response = page("/checks/")
    days = [day.isoformat() for day in response.context["days"]]
    assert days == ["2026-09-27", "2026-09-26", "2026-09-25"]
    statuses = list(response.context["statuses"])
    assert statuses[0] == {"status": STATUS_AVAILABLE, "checks_count": 4}


def test_pagination_keeps_filters(data, monkeypatch):
    monkeypatch.setattr(checks.views, "PAGE_SIZE", 2)
    response = page("/checks/?vendor=openai&sort=old")
    current = response.context["page"]
    assert current.paginator.num_pages == 1
    response = page("/checks/?sort=old")
    current = response.context["page"]
    assert (current.number, current.paginator.num_pages) == (1, 3)
    assert "?sort=old&amp;page=2" in response.content.decode()
    last = page("/checks/?sort=old&page=3").context["page"]
    assert [check.uptime for check in last] == [None]


def test_pagination_wrong_page_number(data, monkeypatch):
    monkeypatch.setattr(checks.views, "PAGE_SIZE", 2)
    assert page("/checks/?page=abc").context["page"].number == 1
    assert page("/checks/?page=99").context["page"].number == 3


def test_search_address_redirects_to_history(data):
    response = Client().get("/checks/search/?q=gpt")
    assert response.status_code == 302
    assert response["Location"] == "/checks/?q=gpt"


def test_import_pr7_keeps_ids_and_relations(data, tmp_path):
    folder, _ = data
    source = tmp_path / "pr7.sqlite"
    import_json_to_sqlite(
        folder / "watchlist.json", folder / "history.json", source
    )
    assert import_pr7(source) == (3, 3, 5)
    gpt = AIModel.objects.get(openrouter_id="openai/gpt-4o-mini")
    assert gpt.id == 1
    assert gpt.vendor.slug == "openai"
    assert gpt.checks.count() == 2
    assert not AIModel.objects.get(openrouter_id="old/model").is_tracked
