"""Тесты веб-интерфейса: маршруты, view-функции и HTTP-ответы.

Данные и запросы к OpenRouter подменяются, чтобы тесты не зависели
от JSON-файлов проекта и от сети.
"""

import pytest
from django.test import Client, override_settings
from django.urls import resolve

import checks.views
import watchlist.views
from models import AIModel, CheckResult, Provider
from models.provider import STATUS_AVAILABLE, STATUS_DOWN


@pytest.fixture
def models():
    return [
        AIModel("openai/gpt-4o-mini", "OpenAI: GPT-4o-mini"),
        AIModel("google/gemma:free", "Google: Gemma (free)"),
    ]


@pytest.fixture
def history(models):
    gpt, gemma = models
    return [
        CheckResult(gpt, STATUS_AVAILABLE, 99.0, "2026-09-26 10:00"),
        CheckResult(gemma, STATUS_DOWN, None, "2026-09-26 10:00"),
        CheckResult(gpt, STATUS_AVAILABLE, 100.0, "2026-09-26 11:00"),
    ]


@pytest.fixture
def client(monkeypatch, models, history):
    """Тестовый клиент Django с подменёнными данными и OpenRouter."""
    for module in (watchlist.views, checks.views):
        monkeypatch.setattr(module, "load_watchlist", lambda: models)
        monkeypatch.setattr(module, "load_history", lambda _models: history)
    providers = [
        Provider("OpenAI", 0, 99.5, 99.8, 99.9),
        Provider("Azure", -1, 0.0, 10.0, 80.0),
    ]
    monkeypatch.setattr(
        watchlist.views, "fetch_providers", lambda _model_id: providers
    )
    return Client()


def test_resolve_model_id_with_slash():
    match = resolve("/models/openai/gpt-4o-mini/")
    assert match.func == watchlist.views.model_detail
    assert match.kwargs == {"model_id": "openai/gpt-4o-mini"}


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "<title>AIMonitor</title>" in text
    assert 'href="/models/"' in text
    assert "bootstrap" in text


def test_models_list(client):
    response = client.get("/models/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "OpenAI: GPT-4o-mini" in text
    assert 'href="/models/google/gemma:free/"' in text
    assert "free</span>" in text


def test_models_list_sorted_by_uptime(client):
    text = client.get("/models/?sort=uptime").content.decode()
    assert text.index("OpenAI: GPT-4o-mini") < text.index("Google: Gemma")


def test_models_list_unknown_sort_ignored(client):
    assert client.get("/models/?sort=bad").status_code == 200


def test_model_detail(client):
    response = client.get("/models/openai/gpt-4o-mini/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "<title>OpenAI: GPT-4o-mini</title>" in text
    assert "Работают 1 из 2 провайдеров" in text
    assert "Azure" in text
    assert "Проверок: 2" in text


def test_model_detail_with_colon_in_id(client):
    response = client.get("/models/google/gemma:free/")
    assert response.status_code == 200
    assert "бесплатная" in response.content.decode()


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


def test_model_name_is_escaped(client, models):
    models.append(AIModel("evil/model", "<script>alert(1)</script>"))
    text = client.get("/models/").content.decode()
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_history_newest_first(client):
    response = client.get("/checks/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "Всего проверок: 3" in text
    assert text.index("11:00") < text.index("10:00")


def test_stats(client):
    response = client.get("/checks/stats/")
    assert response.status_code == 200
    text = response.content.decode()
    assert "Самая стабильная" in text
    assert "Самая проблемная" in text
    assert "100%" in text


def test_unknown_url(client):
    assert client.get("/no-such-page/").status_code == 404


@override_settings(DEBUG=False)
def test_custom_404_page(client):
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "404 – страница не найдена" in response.content.decode()
