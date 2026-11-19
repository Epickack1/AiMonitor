"""Тесты админ-панели и контекстного процессора.

Для модуля создаётся тестовая база Django с одной моделью и проверкой
и тестовый администратор; клиент входит под ним через force_login().
"""

import datetime

import pytest
from django.contrib.auth.models import User
from django.db import DatabaseError
from django.test import Client
from django.test.utils import setup_databases, teardown_databases
from django.utils import timezone

import homepage.context_processors
from checks.models import Check
from watchlist.models import AIModel, Vendor


@pytest.fixture(scope="module")
def admin_client():
    old_config = setup_databases(verbosity=0, interactive=False)
    vendor = Vendor.objects.create(slug="openai", name="OpenAI")
    model = AIModel.objects.create(
        openrouter_id="openai/gpt-4o-mini", name="OpenAI: GPT-4o-mini",
        vendor=vendor,
    )
    Check.objects.create(
        model=model, status=Check.Status.AVAILABLE, uptime=99.0,
        checked_at=timezone.make_aware(datetime.datetime(2026, 9, 26, 10)),
    )
    client = Client()
    client.force_login(User.objects.create_superuser("admin", "", "x"))
    yield client
    teardown_databases(old_config, verbosity=0)


def test_admin_index_is_localized(admin_client):
    text = admin_client.get("/admin/").content.decode()
    assert "AIMonitor — администрирование" in text
    assert "Отслеживание моделей" in text
    assert "Проверки доступности" in text


def test_admin_changelists(admin_client):
    for url in ("/admin/watchlist/vendor/", "/admin/watchlist/aimodel/",
                "/admin/checks/check/"):
        assert admin_client.get(url).status_code == 200


def test_admin_check_search_and_filter(admin_client):
    response = admin_client.get("/admin/checks/check/?q=gpt")
    assert response.context["cl"].result_count == 1
    response = admin_client.get("/admin/checks/check/?status__exact=down")
    assert response.context["cl"].result_count == 0


def test_admin_inline_and_view_on_site(admin_client):
    model = AIModel.objects.get()
    text = admin_client.get(
        f"/admin/watchlist/aimodel/{model.pk}/change/"
    ).content.decode()
    assert "Проверки" in text or "проверки" in text
    assert "Смотреть на сайте" in text
    vendor_page = admin_client.get(
        f"/admin/watchlist/vendor/{model.vendor.pk}/change/"
    ).content.decode()
    assert "openai/gpt-4o-mini" in vendor_page


def test_context_processor(admin_client):
    text = Client().get("/checks/").content.decode()
    assert 'Модели <span class="badge bg-secondary">1</span>' in text
    context = homepage.context_processors.site(None)
    assert context == {"site_name": "AIMonitor", "tracked_models_count": 1}


def test_context_processor_without_tables(admin_client, monkeypatch):
    def broken(*args, **kwargs):
        raise DatabaseError("no such table: watchlist_aimodel")

    monkeypatch.setattr(AIModel.objects, "filter", broken)
    context = homepage.context_processors.site(None)
    assert context["tracked_models_count"] is None


def test_admin_vendor_has_logo_upload(admin_client):
    vendor = Vendor.objects.get()
    text = admin_client.get(
        f"/admin/watchlist/vendor/{vendor.pk}/change/"
    ).content.decode()
    assert 'name="logo"' in text
    assert 'enctype="multipart/form-data"' in text
