"""Страницы отслеживаемых моделей: список и подробная информация."""

from django.http import HttpResponse
from django.utils.html import escape

from homepage.views import page, status_badge
from models import AIModel, CheckResult, ModelStats, Provider
from models.ai_model import find_model
from models.check import iter_results, last_result, sort_models
from models.provider import count_working
from openrouter import fetch_providers
from storage import load_history, load_watchlist
from utils import format_uptime

HISTORY_LIMIT = 10

SORT_LABELS = {
    "": "как добавлены",
    "name": "по названию",
    "uptime": "по аптайму",
}


def sort_links(current: str) -> str:
    """Кнопки выбора порядка сортировки списка моделей."""
    links = ""
    for key, label in SORT_LABELS.items():
        css = "btn-dark" if key == current else "btn-outline-dark"
        href = f"/models/?sort={key}" if key else "/models/"
        links += f'<a href="{href}" class="btn btn-sm {css}">{label}</a>'
    return f'<div class="btn-group mb-3">{links}</div>'


def models_list(request):
    """Страница /models/: отслеживаемые модели и их последняя проверка."""
    models = load_watchlist()
    history = load_history(models)

    sort = request.GET.get("sort", "")
    if sort not in SORT_LABELS:
        sort = ""
    if sort:
        models = sort_models(models, history, by_uptime=sort == "uptime")

    rows = ""
    for model in models:
        result = last_result(history, model.id)
        if result is None:
            last_check = '<span class="text-muted">не проверялась</span>'
            uptime = ""
        else:
            last_check = f"{status_badge(result.status)} {result.checked_at}"
            uptime = format_uptime(result.uptime)
        free = ' <span class="badge bg-info text-dark">free</span>'
        rows += f"""
        <tr>
            <td>
                <a href="/models/{escape(model.id)}/">{escape(model.name)}</a>
                {free if model.is_free else ""}
            </td>
            <td><code>{escape(model.id)}</code></td>
            <td>{last_check}</td>
            <td>{uptime}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="4">Список отслеживания пуст.</td></tr>'

    content = f"""
    <h1>Отслеживаемые модели</h1>
    <p class="text-muted">Всего моделей: {len(models)}</p>
    {sort_links(sort)}
    <div class="table-responsive">
    <table class="table table-hover align-middle">
        <thead class="table-light">
            <tr>
                <th>Модель</th>
                <th>ID в OpenRouter</th>
                <th>Последняя проверка</th>
                <th>Аптайм</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    </div>
    """
    return HttpResponse(page("AIMonitor – модели", content))


def providers_table(providers: list[Provider]) -> str:
    """Таблица провайдеров модели с их состоянием и аптаймом."""
    rows = ""
    for provider in providers:
        if provider.is_working:
            state = '<span class="badge bg-success">работает</span>'
        else:
            state = '<span class="badge bg-danger">сбой</span>'
        rows += f"""
        <tr>
            <td>{escape(provider.name)}</td>
            <td>{state}</td>
            <td>{format_uptime(provider.uptime_5m)}</td>
            <td>{format_uptime(provider.uptime_30m)}</td>
            <td>{format_uptime(provider.uptime_1d)}</td>
        </tr>
        """
    return f"""
    <div class="table-responsive">
    <table class="table table-sm align-middle">
        <thead class="table-light">
            <tr>
                <th>Провайдер</th>
                <th>Состояние</th>
                <th>5 мин</th>
                <th>30 мин</th>
                <th>Сутки</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    </div>
    """


def model_detail(request, model_id):
    """Страница /models/<id>/: текущий статус, провайдеры и история.

    Статус запрашивается у OpenRouter при открытии страницы, но в историю
    не записывается: GET-запрос не должен изменять данные приложения.
    """
    models = load_watchlist()
    model = find_model(models, model_id)

    if model is None:
        content = f"""
        <h1 class="text-danger">Модель не найдена</h1>
        <p>Модели <code>{escape(model_id)}</code> нет в списке
        отслеживания.</p>
        <a href="/models/" class="btn btn-outline-secondary">
            ← к списку моделей
        </a>
        """
        return HttpResponse(page("Модель не найдена", content), status=404)

    result = CheckResult.from_providers(model, fetch_providers(model.id))
    if result.providers:
        working = count_working(result.providers)
        providers = f"""
        <p>Работают {working} из {len(result.providers)} провайдеров.</p>
        {providers_table(result.providers)}
        """
    else:
        providers = """
        <p class="text-muted">Нет данных о провайдерах: модели нет
        в OpenRouter или нет связи с сервисом.</p>
        """

    content = f"""
    {model_card(model, result)}
    <h2 class="h4">Провайдеры</h2>
    {providers}
    <h2 class="h4 mt-4">История проверок</h2>
    {model_history(model, load_history(models))}
    <a href="/models/" class="btn btn-outline-secondary">
        ← к списку моделей
    </a>
    """
    return HttpResponse(page(escape(model.name), content), status=200)


def model_card(model: AIModel, result: CheckResult) -> str:
    """Карточка модели с её текущим статусом."""
    free = "бесплатная" if model.is_free else "платная"
    return f"""
    <div class="card mb-4">
        <div class="card-body">
            <h1 class="card-title h3">{escape(model.name)}</h1>
            <p class="card-text"><strong>ID:</strong>
                <code>{escape(model.id)}</code></p>
            <p class="card-text"><strong>Тип:</strong> {free}</p>
            <p class="card-text"><strong>Статус сейчас:</strong>
                {status_badge(result.status)}
                аптайм {format_uptime(result.uptime)}</p>
        </div>
    </div>
    """


def model_history(model: AIModel, history: list[CheckResult]) -> str:
    """Сводка и последние проверки модели, новые сверху."""
    results = list(iter_results(history, model.id))
    if not results:
        return '<p class="text-muted">Модель ещё не проверялась.</p>'

    stats = ModelStats(model)
    for result in results:
        stats.add(result)

    rows = ""
    for result in reversed(results[-HISTORY_LIMIT:]):
        rows += f"""
        <tr>
            <td>{result.checked_at}</td>
            <td>{status_badge(result.status)}</td>
            <td>{format_uptime(result.uptime)}</td>
        </tr>
        """
    return f"""
    <p>
        Проверок: {stats.checks}, доступна в {stats.percent:.0f}% проверок,
        средний аптайм {format_uptime(stats.avg_uptime)}.
    </p>
    <table class="table table-sm">
        <thead class="table-light">
            <tr><th>Время</th><th>Статус</th><th>Аптайм</th></tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """
