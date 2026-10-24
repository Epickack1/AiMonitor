"""Страницы истории проверок и статистики доступности моделей."""

from django.shortcuts import render

from models.check import collect_stats
from storage import load_history, load_watchlist

HISTORY_LIMIT = 100


def history(request):
    """Страница /checks/: последние проверки всех моделей, новые сверху."""
    results = load_history(load_watchlist())
    context = {
        "results": results[-HISTORY_LIMIT:][::-1],
        "total": len(results),
    }
    return render(request, "checks/history.html", context)


def stats(request):
    """Страница /checks/stats/: статистика доступности по истории."""
    results = load_history(load_watchlist())
    context = {
        "model_stats": collect_stats(results),
        "total": len(results),
    }
    return render(request, "checks/stats.html", context)
