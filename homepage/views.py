"""Главная страница и страница ошибки 404."""

from django.db.models import Count, Max
from django.shortcuts import render

from checks.models import Check
from watchlist.models import AIModel


def index(request):
    """Главная страница: назначение приложения, сводка и разделы."""
    summary = Check.objects.aggregate(
        checks_count=Count("id"),
        last_checked_at=Max("checked_at"),
    )
    summary["models_count"] = AIModel.objects.filter(is_tracked=True).count()
    return render(request, "homepage/index.html", {"summary": summary})


def page_not_found(request, exception):
    """Обработчик handler404: страница для адреса без маршрута."""
    return render(request, "404.html", status=404)
