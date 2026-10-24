"""Маршрутизация верхнего уровня: адреса распределяются по приложениям."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("homepage.urls")),
    path("models/", include("watchlist.urls")),
    path("checks/", include("checks.urls")),
]

# Собственная страница 404: действует для всех приложений при DEBUG = False.
handler404 = "homepage.views.page_not_found"
