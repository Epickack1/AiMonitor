"""Результаты проверок в админ-панели."""

from django.contrib import admin

from .models import Check


@admin.register(Check)
class CheckAdmin(admin.ModelAdmin):
    list_display = ("checked_at", "model", "vendor", "status", "uptime")
    list_display_links = ("checked_at", "model")
    list_filter = ("status", "model__vendor", "checked_at")
    search_fields = ("model__name", "model__openrouter_id")
    date_hierarchy = "checked_at"
    ordering = ("-checked_at", "-id")
    list_per_page = 20
    # Модель и разработчик загружаются JOIN вместе с проверками,
    # без отдельного запроса на каждую строку списка
    list_select_related = ("model__vendor",)
    autocomplete_fields = ("model",)

    @admin.display(description="разработчик", ordering="model__vendor__name")
    def vendor(self, check):
        return check.model.vendor
