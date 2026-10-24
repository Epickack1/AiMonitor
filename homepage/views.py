"""Главная страница и страница ошибки 404."""

from django.shortcuts import render

from db.database import fetch_one

SUMMARY_SQL = """
    SELECT
        (SELECT COUNT(*) FROM models WHERE is_tracked = 1) AS models_count,
        COUNT(*) AS checks_count,
        MAX(checked_at) AS last_checked_at
    FROM checks
"""


def index(request):
    """Главная страница: назначение приложения, сводка и разделы."""
    context = {"summary": fetch_one(SUMMARY_SQL)}
    return render(request, "homepage/index.html", context)


def page_not_found(request, exception):
    """Обработчик handler404: страница для адреса без маршрута."""
    return render(request, "404.html", status=404)
