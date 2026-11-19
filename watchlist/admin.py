"""Разработчики и модели ИИ в админ-панели."""

from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from checks.models import Check

from .models import AIModel, Vendor


class AIModelInline(admin.TabularInline):
    """Модели разработчика в его карточке."""

    model = AIModel
    fields = ("name", "openrouter_id", "is_tracked", "is_free")
    readonly_fields = ("is_free",)
    extra = 0
    show_change_link = True


class CheckInline(admin.TabularInline):
    """Последние проверки в карточке модели."""

    model = Check
    fields = ("checked_at", "status", "uptime")
    ordering = ("-checked_at", "-id")
    extra = 0


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "logo_preview", "models_count")
    readonly_fields = ("logo_preview",)
    fields = ("name", "slug", "logo", "logo_preview")
    search_fields = ("name", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = (AIModelInline,)

    def get_queryset(self, request):
        """Число моделей считается одним запросом для всего списка."""
        return super().get_queryset(request).annotate(
            models_count=Count("models")
        )

    @admin.display(description="моделей", ordering="models_count")
    def models_count(self, vendor):
        return vendor.models_count

    @admin.display(description="предпросмотр")
    def logo_preview(self, vendor):
        """Миниатюра загруженного логотипа; format_html экранирует адрес."""
        if not vendor.logo:
            return "—"
        return format_html(
            '<img src="{}" alt="" style="max-height: 40px">', vendor.logo.url
        )


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = (
        "name", "openrouter_id", "vendor", "is_tracked", "is_free",
        "checks_count",
    )
    list_display_links = ("name", "openrouter_id")
    list_editable = ("is_tracked",)
    list_filter = ("is_tracked", "is_free", "vendor")
    search_fields = ("name", "openrouter_id", "vendor__name")
    list_select_related = ("vendor",)
    ordering = ("id",)
    list_per_page = 25
    readonly_fields = ("is_free",)
    inlines = (CheckInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            checks_count=Count("checks")
        )

    @admin.display(description="проверок", ordering="checks_count")
    def checks_count(self, model):
        return model.checks_count
