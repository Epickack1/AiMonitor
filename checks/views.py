"""Страницы истории проверок и статистики доступности моделей.

Данные читаются из моделей Django через ORM.
"""

import datetime

from django.core.paginator import Paginator
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q
from django.db.models.functions import TruncDate
from django.shortcuts import render

from models.provider import STATUS_AVAILABLE
from watchlist.models import AIModel, Vendor

from .models import STATUS_CHOICES, Check

PAGE_SIZE = 10

STATUSES = [status for status, _ in STATUS_CHOICES]

# Ключ из ?sort= → подпись и поля order_by(). Префикс «-» — по убыванию,
# второе поле упорядочивает записи с одинаковым первым.
SORT_OPTIONS = {
    "new": ("сначала новые", ("-checked_at", "-id")),
    "old": ("сначала старые", ("checked_at", "id")),
    "model": ("по модели", ("model__name", "-checked_at")),
    "uptime": (
        "по аптайму",
        (F("uptime").desc(nulls_last=True), "-checked_at"),
    ),
}


def status_counts():
    """Число проверок с каждым статусом: GROUP BY status."""
    return (
        Check.objects.values("status")
        .annotate(checks_count=Count("id"))
        .order_by("-checks_count", "status")
    )


def filter_checks(params) -> tuple:
    """Отфильтровать проверки по параметрам адреса.

    Параметры — строки из request.GET. Каждый проверяется; некорректный
    не применяется, а в список ошибок добавляется сообщение. Возвращает
    набор проверок, ошибки и очищенные значения фильтров.
    """
    errors = []
    checks = Check.objects.all()

    # Дата: строка ГГГГ-ММ-ДД → datetime.date
    day = params.get("day", "").strip()
    if day:
        try:
            checks = checks.filter(
                checked_at__date=datetime.date.fromisoformat(day)
            )
        except ValueError:
            errors.append(
                f"Некорректная дата «{day}»: нужен формат ГГГГ-ММ-ДД."
            )

    # Статус: только из списка допустимых
    status = params.get("status", "")
    if status in STATUSES:
        checks = checks.filter(status=status)
    elif status:
        errors.append(f"Неизвестный статус «{status}».")

    # Разработчик: фильтр по полю модели, связанной через model
    vendor = params.get("vendor", "")
    if vendor:
        checks = checks.filter(model__vendor__slug=vendor)

    # Поиск по названию или id модели (связанная модель AIModel)
    query = params.get("q", "").strip()
    if query:
        checks = checks.filter(
            Q(model__name__icontains=query)
            | Q(model__openrouter_id__icontains=query)
        )

    sort = params.get("sort", "new")
    if sort not in SORT_OPTIONS:
        sort = "new"
    checks = checks.order_by(*SORT_OPTIONS[sort][1])

    filters = {
        "day": day, "status": status, "vendor": vendor,
        "query": query, "sort": sort,
    }
    return checks, errors, filters


def history_rows(checks):
    """Строки таблицы истории: поля проверки и названия из связанных таблиц.

    annotate() с F() берёт названия модели и разработчика через JOIN,
    values() возвращает словари только с нужными полями. Объекты AIModel
    и Vendor не создаются, поэтому select_related() здесь не нужен.
    """
    return checks.annotate(
        model_name=F("model__name"),
        openrouter_id=F("model__openrouter_id"),
        vendor_name=F("model__vendor__name"),
    ).values(
        "checked_at", "status", "uptime",
        "model_name", "openrouter_id", "vendor_name",
    )


def history(request):
    """Страница /checks/: проверки с фильтрами, сортировкой и страницами.

    Paginator делит результат на страницы по PAGE_SIZE проверок.
    get_page() заменяет некорректный номер страницы на первую,
    а слишком большой — на последнюю.
    """
    checks, errors, filters = filter_checks(request.GET)
    rows = history_rows(checks)
    page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))

    days = (
        Check.objects.annotate(day=TruncDate("checked_at"))
        .values_list("day", flat=True)
        .distinct()
        .order_by("-day")
    )
    context = {
        "page": page,
        "errors": errors,
        "filtered": any(
            filters[key] for key in ("day", "status", "vendor", "query")
        ),
        "days": days,
        "statuses": status_counts(),
        "vendors": Vendor.objects.filter(models__isnull=False).distinct(),
        "sort_options": {
            key: label for key, (label, _) in SORT_OPTIONS.items()
        },
        **filters,
    }
    return render(request, "checks/history.html", context)


def stats(request):
    """Страница /checks/stats/: статистика доступности по истории."""
    model_stats = (
        AIModel.objects.annotate(
            checks_count=Count("checks"),
            available_count=Count(
                "checks", filter=Q(checks__status=STATUS_AVAILABLE)
            ),
            avg_uptime=Avg("checks__uptime"),
        )
        .filter(checks_count__gt=0)
        .annotate(
            percent=ExpressionWrapper(
                100.0 * F("available_count") / F("checks_count"),
                output_field=FloatField(),
            ),
            failed_count=F("checks_count") - F("available_count"),
        )
    )
    # Проблемные — все, кроме моделей, у которых успешны все проверки
    problem_models = model_stats.exclude(
        available_count=F("checks_count")
    ).order_by("-failed_count", "openrouter_id")
    # Список, а не QuerySet: шаблону нужен фильтр last, а QuerySet
    # не поддерживает отрицательные индексы
    model_stats = list(model_stats.order_by(
        "-percent", F("avg_uptime").desc(nulls_last=True), "openrouter_id"
    ))

    vendors = (
        Vendor.objects.filter(models__is_tracked=True)
        .annotate(
            models_count=Count("models", distinct=True),
            checks_count=Count("models__checks"),
        )
        .order_by("-models_count", "name")
    )
    context = {
        "model_stats": model_stats,
        "total": Check.objects.count(),
        "problem_models": problem_models,
        "status_counts": status_counts(),
        "vendors": vendors,
    }
    return render(request, "checks/stats.html", context)
