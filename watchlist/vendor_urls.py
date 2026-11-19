"""Маршруты страниц разработчиков. slug — конвертер <slug:...>."""

from django.urls import path

from . import views

app_name = "vendors"

urlpatterns = [
    path("<slug:slug>/", views.vendor_detail, name="detail"),
]
