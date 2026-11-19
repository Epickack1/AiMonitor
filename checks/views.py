"""Страницы истории проверок, статистики и формы проверки.

Данные читаются из моделей Django через ORM, параметры фильтра
и данные проверки проверяются формами из checks/forms.py.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q
from django.shortcuts import get_object_or_404, redirect, render

from watchlist.models import AIModel, Vendor

from .forms import SORT_OPTIONS, CheckFilterForm, CheckForm
from .models import Check

PAGE_SIZE = 10


def status_counts():
    """Число проверок с каждым статусом: GROUP BY status."""
    return (
        Check.objects.values("status")
        .annotate(checks_count=Count("id"))
        .order_by("-checks_count", "status")
    )


def filter_checks(cleaned: dict):
    """Отфильтровать и упорядочить проверки по проверенным значениям формы.

    cleaned — form.cleaned_data: в нём только поля, прошедшие проверку,
    уже преобразованные в нужные типы (дата — datetime.date, разработчик —
    объект Vendor). Поле с ошибкой в cleaned_data не попадает, поэтому
    его фильтр не применяется.
    """
    checks = Check.objects.all()
    if cleaned.get("day"):
        checks = checks.for_date(cleaned["day"])
    if cleaned.get("status"):
        checks = checks.filter(status=cleaned["status"])
    if cleaned.get("vendor"):
        checks = checks.for_vendor(cleaned["vendor"].slug)
    query = cleaned.get("q", "").strip()
    if query:
        checks = checks.filter(
            Q(model__name__icontains=query)
            | Q(model__openrouter_id__icontains=query)
        )
    # Неизвестная сортировка не проходит проверку ChoiceField — «new»
    sort = cleaned.get("sort") or "new"
    return checks.order_by(*SORT_OPTIONS[sort][1])


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
        vendor_slug=F("model__vendor__slug"),
    ).values(
        "id", "checked_at", "status", "uptime",
        "model_name", "openrouter_id", "vendor_name", "vendor_slug",
    )


def history(request):
    """Страница /checks/: проверки с фильтрами, сортировкой и страницами.

    Форма получает GET-параметры: фильтр не меняет данных, а адрес
    с параметрами можно сохранить и открыть повторно. is_valid()
    проверяет и преобразует значения, ошибки остаются в form.errors.
    Paginator делит результат на страницы по PAGE_SIZE проверок;
    get_page() заменяет некорректный номер страницы на первую,
    а слишком большой — на последнюю.
    """
    form = CheckFilterForm(request.GET)
    form.is_valid()
    checks = filter_checks(form.cleaned_data)
    page = Paginator(history_rows(checks), PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    context = {
        "form": form,
        "page": page,
        "filtered": any(
            form.cleaned_data.get(key)
            for key in ("day", "status", "vendor", "q")
        ),
        "sort": form.cleaned_data.get("sort") or "new",
        "sort_options": {
            key: label for key, (label, _) in SORT_OPTIONS.items()
        },
    }
    return render(request, "checks/history.html", context)


def check_detail(request, pk):
    """Страница /checks/<id>/: одна проверка. Нет записи — ответ 404."""
    check = get_object_or_404(
        Check.objects.select_related("model__vendor"), pk=pk
    )
    return render(request, "checks/check_detail.html", {"check": check})


def check_form(request, check=None):
    """Общая обработка формы создания и изменения проверки.

    GET — пустая форма или форма с данными проверки (instance).
    POST — данные из request.POST: при ошибках форма показывается снова
    с введёнными значениями, при успехе проверка сохраняется
    и выполняется перенаправление (POST/Redirect/GET), чтобы повторная
    отправка страницы не создала запись ещё раз.
    """
    if request.method == "POST":
        form = CheckForm(request.POST, instance=check)
        if form.is_valid():
            saved = form.save()
            messages.success(
                request,
                "Проверка изменена." if check else "Проверка добавлена.",
            )
            return redirect("checks:detail", pk=saved.pk)
    else:
        # ?model=<id> со страницы модели — начальное значение поля
        initial = {} if check else {"model": request.GET.get("model")}
        form = CheckForm(instance=check, initial=initial)
    return render(
        request, "checks/check_form.html", {"form": form, "check": check}
    )


def check_create(request):
    """Страница /checks/new/: новая проверка."""
    return check_form(request)


def check_edit(request, pk):
    """Страница /checks/<id>/edit/: изменение существующей проверки."""
    return check_form(request, get_object_or_404(Check, pk=pk))


def stats(request):
    """Страница /checks/stats/: статистика доступности по истории."""
    model_stats = (
        AIModel.objects.annotate(
            checks_count=Count("checks"),
            available_count=Count(
                "checks", filter=Q(checks__status=Check.Status.AVAILABLE)
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
    # Одна строка итогов: общее число проверок и число с каждым статусом.
    # Count с filter=Q(...) считает только записи, подходящие под условие.
    totals = Check.objects.aggregate(
        total=Count("id"),
        **{
            status: Count("id", filter=Q(status=status))
            for status in Check.Status.values
        },
    )
    context = {
        "model_stats": model_stats,
        "total": totals["total"],
        "totals": [
            (status, label, totals[status])
            for status, label in Check.Status.choices
        ],
        "problem_models": problem_models,
        "status_counts": status_counts(),
        "vendors": vendors,
    }
    return render(request, "checks/stats.html", context)
