"""Результаты проверок в админ-панели."""

from django.contrib import admin

from .models import Check


@admin.register(Check)
class CheckAdmin(admin.ModelAdmin):
    list_display = ("model", "status", "uptime", "checked_at")
    list_filter = ("status", "model__vendor", "checked_at")
    search_fields = ("model__name", "model__openrouter_id")
    date_hierarchy = "checked_at"
