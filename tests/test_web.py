"""Тесты веб-интерфейса: маршруты, view-функции, шаблоны и HTTP-ответы.

Страницы читают данные из SQLite. Для тестов временная база создаётся
скриптом db/import_json.py из тестовых JSON-файлов, запросы к OpenRouter
подменяются, поэтому тесты не зависят от данных проекта и от сети.
"""

import sqlite3

import pytest
from django.test import Client, override_settings
from django.urls import resolve

import db.database
import watchlist.views
from db.import_json import main as import_json
from models import AIModel, CheckResult, Provider
from models.provider import STATUS_AVAILABLE, STATUS_DOWN
from storage import save_history, save_watchlist


@pytest.fixture
def models():
    return [
        AIModel("openai/gpt-4o-mini", "OpenAI: GPT-4o-mini"),
        AIModel("google/gemma:free", "Google: Gemma (free)"),
    ]


@pytest.fixture
def history(models):
    gpt, gemma = models
    removed = AIModel("old/model", "old/model")
    return [
        CheckResult(removed, STATUS_AVAILABLE, 90.0, "2026-09-25 09:00"),
        CheckResult(gpt, STATUS_AVAILABLE, 99.0, "2026-09-26 10:00"),
        CheckResult(gemma, STATUS_DOWN, None, "2026-09-26 10:00"),
        CheckResult(gpt, STATUS_AVAILABLE, 100.0, "2026-09-27 11:00"),
    ]


@pytest.fixture
def database(tmp_path, monkeypatch, models, history):
    """Временная база SQLite, заполненная из JSON скриптом импорта."""
    watchlist_file = tmp_path / "watchlist.json"
    history_file = tmp_path / "history.json"
    db_file = tmp_path / "test.sqlite"
    save_watchlist(models, watchlist_file)
    save_history(history, history_file)
    import_json(watchlist_file, history_file, db_file)
    monkeypatch.setattr(db.database, "DB_PATH", db_file)
    return db_file


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


def test_import_json(database):
    conn = db.database.get_connection(database)
    counts = [
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("vendors", "models", "checks")
    ]
    tracked = conn.execute(
        "SELECT openrouter_id FROM models WHERE is_tracked = 0"
    ).fetchall()
    conn.close()
    assert counts == [3, 3, 4]
    assert tracked == [("old/model",)]


def test_import_json_can_be_repeated(database, tmp_path):
    assert import_json(
        tmp_path / "watchlist.json", tmp_path / "history.json", database
    ) == (3, 4)


def test_foreign_keys_are_checked(database):
    conn = db.database.get_connection(database)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO checks (model_id, status, checked_at)"
            " VALUES (999, 'x', '2026-01-01 00:00')"
        )
    conn.close()


def test_like_pattern_escapes_wildcards():
    assert watchlist.views.like_pattern("50%_a") == "%50\\%\\_a%"


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
    assert summary["last_checked_at"] == "2026-09-27 11:00"


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
    assert first["openrouter_id"] == "openai/gpt-4o-mini"
    assert first["uptime"] == 100.0
    assert first["checked_at"] == "2026-09-27 11:00"
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
    names = [row["name"] for row in response.context["models"]]
    assert names == ["Google: Gemma (free)"]


def test_models_list_search_is_parameterized(client):
    response = client.get("/models/?q=' OR 1=1 --")
    assert response.status_code == 200
    assert "Подходящих моделей нет" in response.content.decode()


def test_models_list_free_only(client):
    response = client.get("/models/?free=1")
    ids = [row["openrouter_id"] for row in response.context["models"]]
    assert ids == ["google/gemma:free"]


def test_models_list_unknown_sort_ignored(client):
    assert client.get("/models/?sort=bad").status_code == 200


def test_model_detail(client):
    response = client.get("/models/openai/gpt-4o-mini/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "<title>OpenAI: GPT-4o-mini – AIMonitor</title>" in text
    assert "watchlist/includes/model_card.html" in template_names(response)
    assert "Работают 1 из 2 провайдеров" in text
    assert "Azure" in text
    assert "Проверок: 2" in text
    assert "Разработчик:</strong> OpenAI" in text
    history = response.context["history"]
    assert [row["checked_at"] for row in history] == [
        "2026-09-27 11:00", "2026-09-26 10:00"
    ]


def test_model_detail_with_colon_in_id(client):
    response = client.get("/models/google/gemma:free/")
    assert response.status_code == 200
    assert "бесплатная" in response.content.decode()


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


def test_model_name_is_escaped(client, database):
    conn = db.database.get_connection(database)
    conn.execute(
        "INSERT INTO models (openrouter_id, name, vendor_id)"
        " VALUES ('evil/model', '<script>alert(1)</script>', 1)"
    )
    conn.commit()
    conn.close()
    text = client.get("/models/").content.decode()
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_history_newest_first(client):
    response = client.get("/checks/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "Всего проверок: 4" in text
    assert text.index("2026-09-27 11:00") < text.index("2026-09-26 10:00")


def test_history_filter_by_day_and_status(client):
    response = client.get(f"/checks/?day=2026-09-26&status={STATUS_DOWN}")
    assert response.context["total"] == 1
    assert response.context["results"][0]["model_name"] == (
        "Google: Gemma (free)"
    )
    assert "Найдено проверок: 1" in response.content.decode()


def test_history_filter_without_matches(client):
    response = client.get("/checks/?day=2000-01-01")
    assert response.context["total"] == 0
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
    names = [row["name"] for row in response.context["model_stats"]]
    assert names == ["OpenAI: GPT-4o-mini", "old/model",
                     "Google: Gemma (free)"]
    problems = response.context["problem_models"]
    assert [row["name"] for row in problems] == ["Google: Gemma (free)"]
    statuses = {row["status"]: row["checks_count"]
                for row in response.context["status_counts"]}
    assert statuses == {STATUS_AVAILABLE: 3, STATUS_DOWN: 1}
    vendors = [row["vendor_name"] for row in response.context["vendors"]]
    assert vendors == ["Google", "OpenAI"]


def test_unknown_url(client):
    assert client.get("/no-such-page/").status_code == 404


@override_settings(DEBUG=False)
def test_custom_404_page(client):
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "404 – страница не найдена" in response.content.decode()
