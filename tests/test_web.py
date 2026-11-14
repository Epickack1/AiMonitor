"""Тесты веб-интерфейса: маршруты, view-функции, шаблоны и HTTP-ответы.

Страницы читают данные из моделей Django через ORM. Для модуля создаётся
тестовая база Django и заполняется командой import_json из тестовых
JSON-файлов, запросы к OpenRouter подменяются, поэтому тесты
не зависят от данных проекта и от сети.
"""

import pytest
from django.test import Client, override_settings
from django.test.utils import setup_databases, teardown_databases
from django.urls import resolve

import watchlist.views
from checks.management.commands.import_json import import_data
from models import AIModel, CheckResult, Provider
from models.provider import STATUS_AVAILABLE, STATUS_DOWN
from storage import save_history, save_watchlist
from watchlist.models import AIModel as AIModelRecord
from watchlist.models import Vendor


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    """Тестовая база Django: две отслеживаемые модели, одна удалённая."""
    old_config = setup_databases(verbosity=0, interactive=False)
    gpt = AIModel("openai/gpt-4o-mini", "OpenAI: GPT-4o-mini")
    gemma = AIModel("google/gemma:free", "Google: Gemma (free)")
    removed = AIModel("old/model", "old/model")
    folder = tmp_path_factory.mktemp("json")
    save_watchlist([gpt, gemma], folder / "watchlist.json")
    save_history(
        [
            CheckResult(removed, STATUS_AVAILABLE, 90.0, "2026-09-25 09:00"),
            CheckResult(gpt, STATUS_AVAILABLE, 99.0, "2026-09-26 10:00"),
            CheckResult(gemma, STATUS_DOWN, None, "2026-09-26 10:00"),
            CheckResult(gpt, STATUS_AVAILABLE, 100.0, "2026-09-27 11:00"),
        ],
        folder / "history.json",
    )
    import_data(folder / "watchlist.json", folder / "history.json")
    yield
    teardown_databases(old_config, verbosity=0)


@pytest.fixture
def client(database, monkeypatch):
    """Тестовый клиент Django с подменёнными данными OpenRouter."""
    providers = [
        Provider("OpenAI", 0, 99.5, 99.8, 99.9),
        Provider("Azure", -1, 0.0, 10.0, 80.0),
    ]
    monkeypatch.setattr(
        watchlist.views, "fetch_providers", lambda _model_id: providers
    )
    return Client()


def template_names(response):
    return [template.name for template in response.templates]


def test_resolve_model_id_with_slash():
    match = resolve("/models/openai/gpt-4o-mini/")
    assert match.func == watchlist.views.model_detail
    assert match.kwargs == {"model_id": "openai/gpt-4o-mini"}


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "<title>Главная – AIMonitor</title>" in text
    assert 'href="/models/"' in text
    assert "bootstrap" in text
    assert "/static/homepage/css/style.css" in text
    assert "/static/homepage/js/main.js" in text
    summary = response.context["summary"]
    assert summary["models_count"] == 2
    assert summary["checks_count"] == 4
    assert "2026-09-27 11:00" in text


def test_pages_extend_base_template(client):
    for url in ("/", "/models/", "/models/openai/gpt-4o-mini/",
                "/checks/", "/checks/stats/"):
        names = template_names(client.get(url))
        assert "base.html" in names
        assert "includes/navigation.html" in names


def test_models_list(client):
    response = client.get("/models/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "OpenAI: GPT-4o-mini" in text
    assert 'href="/models/google/gemma:free/"' in text
    assert "free</span>" in text
    assert "old/model" not in text


def test_models_list_shows_last_check(client):
    response = client.get("/models/")
    first = response.context["models"][0]
    assert first.openrouter_id == "openai/gpt-4o-mini"
    assert first.last_uptime == 100.0
    assert first.last_status == STATUS_AVAILABLE
    assert "2026-09-27 11:00" in response.content.decode()
    assert template_names(response).count(
        "watchlist/includes/model_row.html"
    ) == 2


def test_models_list_sorted_by_uptime(client):
    text = client.get("/models/?sort=uptime").content.decode()
    assert text.index("OpenAI: GPT-4o-mini") < text.index("Google: Gemma")


def test_models_list_sorted_by_name(client):
    text = client.get("/models/?sort=name").content.decode()
    assert text.index("Google: Gemma") < text.index("OpenAI: GPT-4o-mini")


def test_models_list_search(client):
    response = client.get("/models/?q=GEMMA")
    names = [model.name for model in response.context["models"]]
    assert names == ["Google: Gemma (free)"]


def test_models_list_search_special_characters(client):
    for query in ("' OR 1=1 --", "%", "_"):
        response = client.get("/models/", {"q": query})
        assert response.status_code == 200
        assert "Подходящих моделей нет" in response.content.decode()


def test_models_list_free_only(client):
    response = client.get("/models/?free=1")
    ids = [model.openrouter_id for model in response.context["models"]]
    assert ids == ["google/gemma:free"]


def test_models_list_sort_keeps_search(client):
    text = client.get("/models/?q=gpt&free=1").content.decode()
    assert "?q=gpt&amp;free=1&amp;sort=name" in text


def test_models_list_unknown_sort_ignored(client):
    response = client.get("/models/?sort=bad")
    assert response.status_code == 200
    assert response.context["sort"] == ""


def test_model_detail(client):
    response = client.get("/models/openai/gpt-4o-mini/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "<title>OpenAI: GPT-4o-mini – AIMonitor</title>" in text
    assert "watchlist/includes/model_card.html" in template_names(response)
    assert "Работают 1 из 2 провайдеров" in text
    assert "Azure" in text
    assert "Проверок: 2" in text
    assert response.context["summary"]["percent"] == 100
    assert "Разработчик:</strong> OpenAI" in text
    history = response.context["history"]
    assert [check.uptime for check in history] == [100.0, 99.0]
    assert text.index("2026-09-27 11:00") < text.index("2026-09-26 10:00")


def test_model_detail_with_colon_in_id(client):
    response = client.get("/models/google/gemma:free/")
    assert response.status_code == 200
    assert "бесплатная" in response.content.decode()
    assert response.context["summary"]["percent"] == 0


def test_model_detail_of_untracked_model(client):
    response = client.get("/models/old/model/")
    assert response.status_code == 200
    assert "не отслеживается" in response.content.decode()


def test_model_detail_not_found(client):
    response = client.get("/models/unknown/model/")
    assert response.status_code == 404
    assert "Модель не найдена" in response.content.decode()


def test_model_detail_without_network(client, monkeypatch):
    monkeypatch.setattr(
        watchlist.views, "fetch_providers", lambda _model_id: None
    )
    response = client.get("/models/openai/gpt-4o-mini/")
    assert response.status_code == 200
    assert "Нет данных о провайдерах" in response.content.decode()


def test_model_name_is_escaped(client):
    evil = AIModelRecord.objects.create(
        openrouter_id="evil/model",
        name="<script>alert(1)</script>",
        vendor=Vendor.objects.get(slug="openai"),
    )
    try:
        text = client.get("/models/").content.decode()
    finally:
        evil.delete()
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text
    assert "не проверялась" in text


def test_history_newest_first(client):
    response = client.get("/checks/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "Всего проверок: 4" in text
    assert text.index("2026-09-27 11:00") < text.index("2026-09-26 10:00")


def test_history_filter_by_day_and_status(client):
    response = client.get(f"/checks/?day=2026-09-26&status={STATUS_DOWN}")
    page = response.context["page"]
    assert page.paginator.count == 1
    assert page[0].model.name == "Google: Gemma (free)"
    assert "Найдено проверок: 1" in response.content.decode()


def test_history_filter_without_matches(client):
    response = client.get("/checks/?day=2000-01-01")
    assert response.context["page"].paginator.count == 0
    assert "Проверок с выбранными условиями нет" in (
        response.content.decode()
    )


def test_stats(client):
    response = client.get("/checks/stats/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "Самая стабильная" in text
    assert "Самая проблемная" in text
    assert "100%" in text
    assert response.context["total"] == 4
    stats = response.context["model_stats"]
    assert [item.name for item in stats] == [
        "OpenAI: GPT-4o-mini", "old/model", "Google: Gemma (free)"
    ]
    assert [item.percent for item in stats] == [100.0, 100.0, 0.0]
    problems = response.context["problem_models"]
    assert [(item.name, item.failed_count) for item in problems] == [
        ("Google: Gemma (free)", 1)
    ]
    statuses = {row["status"]: row["checks_count"]
                for row in response.context["status_counts"]}
    assert statuses == {STATUS_AVAILABLE: 3, STATUS_DOWN: 1}
    vendors = [(item.name, item.models_count, item.checks_count)
               for item in response.context["vendors"]]
    assert vendors == [("Google", 1, 1), ("OpenAI", 1, 2)]


def test_unknown_url(client):
    assert client.get("/no-such-page/").status_code == 404


@override_settings(DEBUG=False)
def test_custom_404_page(client):
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "404 – страница не найдена" in response.content.decode()
