"""Страницы отслеживаемых моделей: список и подробная информация."""

from django.shortcuts import render

from models import CheckResult, ModelStats
from models.ai_model import find_model
from models.check import iter_results, last_result, sort_models
from models.provider import count_working
from openrouter import fetch_providers
from storage import load_history, load_watchlist

HISTORY_LIMIT = 10

SORT_OPTIONS = {
    "": "как добавлены",
    "name": "по названию",
    "uptime": "по аптайму",
}


def models_list(request):
    """Страница /models/: отслеживаемые модели и их последняя проверка."""
    models = load_watchlist()
    history = load_history(models)

    sort = request.GET.get("sort", "")
    if sort not in SORT_OPTIONS:
        sort = ""
    if sort:
        models = sort_models(models, history, by_uptime=sort == "uptime")

    items = [
        {"model": model, "result": last_result(history, model.id)}
        for model in models
    ]
    context = {
        "items": items,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
    }
    return render(request, "watchlist/model_list.html", context)


def model_detail(request, model_id):
    """Страница /models/<id>/: текущий статус, провайдеры и история.

    Статус запрашивается у OpenRouter при открытии страницы, но в историю
    не записывается: GET-запрос не должен изменять данные приложения.
    """
    models = load_watchlist()
    model = find_model(models, model_id)
    context = {"model": model, "model_id": model_id}

    if model is not None:
        result = CheckResult.from_providers(model, fetch_providers(model.id))
        results = list(iter_results(load_history(models), model.id))
        stats = ModelStats(model)
        for item in results:
            stats.add(item)
        context.update({
            "result": result,
            "working": count_working(result.providers),
            "history": results[-HISTORY_LIMIT:][::-1],
            "stats": stats,
        })

    return render(
        request,
        "watchlist/model_detail.html",
        context,
        status=404 if model is None else 200,
    )
