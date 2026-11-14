"""Разработчики и модели ИИ в админ-панели."""

from django.contrib import admin

from .models import AIModel, Vendor


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ("name", "openrouter_id", "vendor", "is_tracked")
    list_filter = ("is_tracked", "vendor")
    search_fields = ("name", "openrouter_id")
