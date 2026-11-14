"""Страницы отслеживаемых моделей: список и подробная информация.

Данные читаются из моделей Django через ORM, текущее состояние
провайдеров — из OpenRouter.
"""

from django.db.models import Avg, Count, F, OuterRef, Q, Subquery
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from checks.models import Check
from models import AIModel as DomainModel
from models import CheckResult
from models.provider import STATUS_AVAILABLE, count_working
from openrouter import fetch_providers

from .models import FREE_SUFFIX, AIModel

HISTORY_LIMIT = 10

# Ключ из ?sort= → подпись и поля order_by(). Пользовательское значение
# в order_by() не передаётся: неизвестный ключ заменяется на "".
SORT_OPTIONS = {
    "": ("как добавлены", ("id",)),
    "name": ("по названию", (Lower("name"), "id")),
    "uptime": (
        "по аптайму",
        (F("last_uptime").desc(nulls_last=True), "id"),
    ),
}


def with_last_check(models):
    """Добавить к моделям статус, аптайм и время последней проверки.

    Подзапрос выбирает самую новую проверку каждой модели (OuterRef —
    ссылка на модель из внешнего запроса). Модели без проверок остаются
    в списке со значениями None.
    """
    last = Check.objects.filter(model=OuterRef("pk")).order_by(
        "-checked_at", "-id"
    )
    return models.annotate(
        last_status=Subquery(last.values("status")[:1]),
        last_uptime=Subquery(last.values("uptime")[:1]),
        last_checked_at=Subquery(last.values("checked_at")[:1]),
    )


def models_list(request):
    """Страница /models/: поиск, фильтр и сортировка моделей."""
    sort = request.GET.get("sort", "")
    if sort not in SORT_OPTIONS:
        sort = ""
    query = request.GET.get("q", "").strip()
    free_only = request.GET.get("free") == "1"

    models = with_last_check(AIModel.objects.filter(is_tracked=True))
    if query:
        models = models.filter(
            Q(name__icontains=query) | Q(openrouter_id__icontains=query)
        )
    if free_only:
        models = models.filter(openrouter_id__endswith=FREE_SUFFIX)
    models = models.order_by(*SORT_OPTIONS[sort][1])

    context = {
        "models": models,
        "sort": sort,
        "sort_options": {
            key: label for key, (label, _) in SORT_OPTIONS.items()
        },
        "query": query,
        "free_only": free_only,
    }
    return render(request, "watchlist/model_list.html", context)


def model_summary(model: AIModel) -> dict:
    """Сводка по проверкам модели: число, доля успешных, средний аптайм."""
    summary = model.checks.aggregate(
        checks_count=Count("id"),
        available_count=Count("id", filter=Q(status=STATUS_AVAILABLE)),
        avg_uptime=Avg("uptime"),
    )
    if summary["checks_count"]:
        summary["percent"] = (
            100 * summary["available_count"] / summary["checks_count"]
        )
    return summary


def model_detail(request, model_id):
    """Страница /models/<id>/: текущий статус, провайдеры и история.

    Статус запрашивается у OpenRouter при открытии страницы, но в историю
    не записывается: GET-запрос не должен изменять данные приложения.
    """
    # get_object_or_404() вызывает get(), а при отсутствии записи вместо
    # DoesNotExist поднимает Http404. Исключение перехватывается, чтобы
    # показать свою страницу «Модель не найдена» с кодом 404.
    try:
        model = get_object_or_404(
            AIModel.objects.select_related("vendor"), openrouter_id=model_id
        )
    except Http404:
        context = {"model": None, "model_id": model_id}
        return render(
            request, "watchlist/model_detail.html", context, status=404
        )

    domain_model = DomainModel(model.openrouter_id, model.name)
    result = CheckResult.from_providers(
        domain_model, fetch_providers(domain_model.id)
    )
    context = {
        "model": model,
        "model_id": model_id,
        "result": result,
        "working": count_working(result.providers),
        "summary": model_summary(model),
        "history": model.checks.order_by("-checked_at", "-id")[
            :HISTORY_LIMIT
        ],
    }
    return render(request, "watchlist/model_detail.html", context)
