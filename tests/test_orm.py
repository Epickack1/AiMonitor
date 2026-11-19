"""Тесты Django-моделей, переноса данных и ORM-запросов истории проверок.

Для модуля создаётся тестовая база Django (в памяти) и заполняется
командой import_json из тестовых JSON-файлов, поэтому тесты
не зависят от данных проекта.
"""

import datetime
import importlib

import pytest
from django.apps import apps as django_apps
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

AVAILABLE = Check.Status.AVAILABLE


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
    return [row["openrouter_id"] for row in response.context["page"]]


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


def test_history_rows_with_related_names_in_one_query(data):
    found, _, _ = checks.views.filter_checks({"vendor": "google"})
    with CaptureQueriesContext(connection) as queries:
        rows = list(checks.views.history_rows(found))
    assert len(queries) == 1
    assert "JOIN" in queries[0]["sql"]
    assert set(rows[0]) == {
        "checked_at", "status", "uptime",
        "model_name", "openrouter_id", "vendor_name", "vendor_slug",
    }
    assert {row["vendor_name"] for row in rows} == {"Google"}


def test_model_detail_loads_vendor_in_one_query(data):
    with CaptureQueriesContext(connection) as queries:
        model = AIModel.objects.select_related("vendor").get(
            openrouter_id="openai/gpt-4o-mini"
        )
        assert model.vendor.name == "OpenAI"
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
        f"/checks/?day=2026-09-27&status={AVAILABLE}&vendor=google"
    )
    assert names(response) == ["google/gemma:free"]


def test_history_search_by_model(data):
    response = page("/checks/?q=GEMMA")
    assert names(response) == ["google/gemma:free", "google/gemma:free"]


def test_history_invalid_date(data):
    response = page(f"/checks/?day=2026-13-45&status={AVAILABLE}")
    assert len(response.context["errors"]) == 1
    assert "Некорректная дата" in response.content.decode()
    assert response.context["page"].paginator.count == 4


def test_history_invalid_status(data):
    response = page("/checks/?status=Ошибка")
    assert "Неизвестный статус" in response.context["errors"][0]
    assert response.context["page"].paginator.count == 5


def test_history_sort(data):
    new = [row["checked_at"] for row in page("/checks/").context["page"]]
    old = [row["checked_at"]
           for row in page("/checks/?sort=old").context["page"]]
    assert new == sorted(new, reverse=True)
    assert old == sorted(old)


def test_history_sort_uptime_nulls_last(data):
    response = page("/checks/?sort=uptime")
    uptimes = [row["uptime"] for row in response.context["page"]]
    assert uptimes == [100.0, 99.0, 90.0, None, None]


def test_history_unknown_sort_ignored(data):
    assert page("/checks/?sort=hack").context["sort"] == "new"


def test_history_days_and_statuses(data):
    response = page("/checks/")
    days = [day.isoformat() for day in response.context["days"]]
    assert days == ["2026-09-27", "2026-09-26", "2026-09-25"]
    statuses = list(response.context["statuses"])
    assert statuses[0] == {"status": AVAILABLE, "checks_count": 4}


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
    assert [row["uptime"] for row in last] == [None]


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


def test_queryset_methods(data):
    day = datetime.date(2026, 9, 27)
    assert Check.objects.available().count() == 4
    assert Check.objects.failed().count() == 1
    assert Check.objects.for_date(day).count() == 2
    assert Check.objects.for_date(day).available().count() == 2
    assert Check.objects.for_vendor("google").failed().count() == 1


def test_status_labels(data):
    check = Check.objects.failed().get()
    assert check.status == Check.Status.NOT_FOUND
    assert check.get_status_display() == STATUS_NOT_FOUND


def test_status_migration_converts_labels(data):
    migration = importlib.import_module(
        "checks.migrations.0002_status_textchoices"
    )
    check = Check.objects.failed().get()
    Check.objects.filter(pk=check.pk).update(status=STATUS_NOT_FOUND)
    migration.labels_to_codes(django_apps, None)
    check.refresh_from_db()
    assert check.status == Check.Status.NOT_FOUND
    migration.codes_to_labels(django_apps, None)
    check.refresh_from_db()
    assert check.status == STATUS_NOT_FOUND
    migration.labels_to_codes(django_apps, None)


def test_generated_field_is_free(data):
    model = AIModel.objects.get(openrouter_id="google/gemma:free")
    assert model.is_free is True
    model.openrouter_id = "google/gemma"
    model.save()
    assert model.is_free is True          # в памяти — старое значение
    model.refresh_from_db()
    assert model.is_free is False         # база пересчитала столбец
    model.openrouter_id = "google/gemma:free"
    model.save()
    assert AIModel.objects.filter(is_free=True).count() == 1


def test_get_absolute_url(data):
    gpt = AIModel.objects.get(openrouter_id="openai/gpt-4o-mini")
    assert gpt.get_absolute_url() == "/models/openai/gpt-4o-mini/"
    assert gpt.vendor.get_absolute_url() == "/vendors/openai/"


def test_vendor_page(data):
    response = page("/vendors/google/")
    assert response.context["vendor"].name == "Google"
    assert [m.openrouter_id for m in response.context["models"]] == [
        "google/gemma:free"
    ]
    assert response.context["summary"]["checks_count"] == 2
    assert Client().get("/vendors/nobody/").status_code == 404


def test_models_without_success_on_day(data):
    response = page("/models/?problem_day=2026-09-26")
    ids = [m.openrouter_id for m in response.context["models"]]
    assert ids == ["google/gemma:free"]
    gemma_check = Check.objects.for_date(
        datetime.date(2026, 9, 27)).get(model__openrouter_id__endswith="free")
    gemma_check.status = Check.Status.DOWN
    gemma_check.save()
    try:
        response = page("/models/?problem_day=2026-09-27")
        assert [m.openrouter_id for m in response.context["models"]] == [
            "google/gemma:free"
        ]
    finally:
        gemma_check.status = Check.Status.AVAILABLE
        gemma_check.save()
    assert list(page("/models/?problem_day=2026-09-27").context["models"]) \
        == []


def test_models_problem_day_invalid(data):
    response = page("/models/?problem_day=2026-02-30")
    assert "Некорректная дата" in response.context["errors"][0]
    assert len(response.context["models"]) == 2


def test_stats_totals_by_status(data):
    totals = {status: count
              for status, _, count in page("/checks/stats/").context["totals"]}
    assert totals == {
        Check.Status.AVAILABLE: 4, Check.Status.UNSTABLE: 0,
        Check.Status.DOWN: 0, Check.Status.NOT_FOUND: 1,
    }
