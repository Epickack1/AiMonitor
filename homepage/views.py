"""Главная страница и страница ошибки 404."""

from django.shortcuts import render


def index(request):
    """Главная страница: назначение приложения и переходы к разделам."""
    return render(request, "homepage/index.html")


def page_not_found(request, exception):
    """Обработчик handler404: страница для адреса без маршрута."""
    return render(request, "404.html", status=404)
