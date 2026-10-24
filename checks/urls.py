"""Маршруты истории проверок и статистики."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.history, name="history"),
    path("stats/", views.stats, name="stats"),
]
