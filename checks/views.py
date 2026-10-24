"""Страницы истории проверок и статистики доступности моделей."""

from django.http import HttpResponse
from django.utils.html import escape

from homepage.views import page, status_badge
from models.check import collect_stats
from storage import load_history, load_watchlist
from utils import format_uptime

HISTORY_LIMIT = 100


def history(request):
    """Страница /checks/: последние проверки всех моделей, новые сверху."""
    results = load_history(load_watchlist())

    rows = ""
    for result in reversed(results[-HISTORY_LIMIT:]):
        model = result.model
        rows += f"""
        <tr>
            <td>{result.checked_at}</td>
            <td><a href="/models/{escape(model.id)}/">{escape(model.name)}</a>
            </td>
            <td>{status_badge(result.status)}</td>
            <td>{format_uptime(result.uptime)}</td>
        </tr>
        """
    if not rows:
        rows = """
        <tr><td colspan="4">
            История пуста. Проверьте модели в консольной версии
            (python main.py, пункт 1).
        </td></tr>
        """

    content = f"""
    <h1>История проверок</h1>
    <p class="text-muted">
        Всего проверок: {len(results)}. Показаны последние
        {min(len(results), HISTORY_LIMIT)}.
    </p>
    <div class="table-responsive">
    <table class="table table-hover align-middle">
        <thead class="table-light">
            <tr>
                <th>Время</th>
                <th>Модель</th>
                <th>Статус</th>
                <th>Аптайм</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    </div>
    """
    return HttpResponse(page("AIMonitor – история проверок", content))


def stats(request):
    """Страница /checks/stats/: статистика доступности по истории."""
    results = load_history(load_watchlist())
    model_stats = collect_stats(results)

    if not model_stats:
        content = """
        <h1>Статистика доступности</h1>
        <p class="text-muted">История пуста: статистику не по чему
        считать.</p>
        """
        return HttpResponse(page("AIMonitor – статистика", content))

    rows = ""
    for item in model_stats:
        model = item.model
        rows += f"""
        <tr>
            <td><a href="/models/{escape(model.id)}/">{escape(model.name)}</a>
            </td>
            <td>{item.checks}</td>
            <td>{item.percent:.0f}%</td>
            <td>{format_uptime(item.avg_uptime)}</td>
        </tr>
        """

    best = escape(model_stats[0].model.name)
    worst = ""
    if len(model_stats) > 1:
        worst = f"""
        <div class="col">
            <div class="card border-danger h-100">
                <div class="card-body">
                    <p class="card-text text-muted mb-1">Самая проблемная</p>
                    <p class="card-text h5">
                        {escape(model_stats[-1].model.name)}</p>
                </div>
            </div>
        </div>
        """

    content = f"""
    <h1>Статистика доступности</h1>
    <p class="text-muted">
        Проверок: {len(results)}, моделей: {len(model_stats)}.
    </p>
    <div class="row row-cols-1 row-cols-md-2 g-3 mb-4">
        <div class="col">
            <div class="card border-success h-100">
                <div class="card-body">
                    <p class="card-text text-muted mb-1">Самая стабильная</p>
                    <p class="card-text h5">{best}</p>
                </div>
            </div>
        </div>
        {worst}
    </div>
    <div class="table-responsive">
    <table class="table table-hover align-middle">
        <thead class="table-light">
            <tr>
                <th>Модель</th>
                <th>Проверок</th>
                <th>Доступна</th>
                <th>Средний аптайм</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    </div>
    """
    return HttpResponse(page("AIMonitor – статистика", content))
