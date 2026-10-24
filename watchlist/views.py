"""Страницы отслеживаемых моделей: список и подробная информация.

Данные читаются из SQLite (data/aimonitor.sqlite) SQL-запросами,
текущее состояние провайдеров — из OpenRouter.
"""

from django.shortcuts import render

from db.database import fetch_all, fetch_one
from models import AIModel, CheckResult
from models.provider import STATUS_AVAILABLE, count_working
from openrouter import fetch_providers

HISTORY_LIMIT = 10

SORT_OPTIONS = {
    "": "как добавлены",
    "name": "по названию",
    "uptime": "по аптайму",
}

# Отслеживаемые модели с последней проверкой. Поиск, фильтр бесплатных
# и порядок сортировки задаются параметрами, текст запроса не меняется.
MODELS_SQL = """
    SELECT
        models.openrouter_id,
        models.name,
        models.openrouter_id LIKE '%:free' AS is_free,
        checks.status,
        checks.uptime,
        checks.checked_at
    FROM models
    LEFT JOIN checks
        ON checks.id = (
            SELECT MAX(last.id)
            FROM checks AS last
            WHERE last.model_id = models.id
        )
    WHERE models.is_tracked = 1
      AND (:query = ''
           OR models.openrouter_id LIKE :pattern ESCAPE '\\'
           OR models.name LIKE :pattern ESCAPE '\\')
      AND (:free_only = 0 OR models.openrouter_id LIKE '%:free')
    ORDER BY
        CASE WHEN :sort = 'uptime' THEN checks.uptime IS NULL END,
        CASE WHEN :sort = 'uptime' THEN checks.uptime END DESC,
        CASE WHEN :sort = 'name' THEN models.name END COLLATE NOCASE,
        models.id
"""

MODEL_SQL = """
    SELECT
        models.openrouter_id,
        models.name,
        models.is_tracked,
        models.openrouter_id LIKE '%:free' AS is_free,
        vendors.name AS vendor_name
    FROM models
    JOIN vendors
        ON models.vendor_id = vendors.id
    WHERE models.openrouter_id = ?
"""

MODEL_SUMMARY_SQL = """
    SELECT
        COUNT(*) AS checks_count,
        ROUND(100.0 * SUM(checks.status = ?) / COUNT(*), 1) AS percent,
        AVG(checks.uptime) AS avg_uptime
    FROM checks
    JOIN models
        ON checks.model_id = models.id
    WHERE models.openrouter_id = ?
"""

MODEL_HISTORY_SQL = """
    SELECT
        checks.checked_at,
        checks.status,
        checks.uptime
    FROM checks
    JOIN models
        ON checks.model_id = models.id
    WHERE models.openrouter_id = ?
    ORDER BY checks.id DESC
    LIMIT ?
"""


def like_pattern(text: str) -> str:
    """Шаблон LIKE «содержит text»: % и _ из запроса ищутся буквально."""
    for char in ("\\", "%", "_"):
        text = text.replace(char, "\\" + char)
    return f"%{text}%"


def models_list(request):
    """Страница /models/: поиск, фильтр и сортировка моделей."""
    sort = request.GET.get("sort", "")
    if sort not in SORT_OPTIONS:
        sort = ""
    query = request.GET.get("q", "").strip()
    free_only = request.GET.get("free") == "1"

    models = fetch_all(MODELS_SQL, {
        "query": query,
        "pattern": like_pattern(query),
        "free_only": int(free_only),
        "sort": sort,
    })
    context = {
        "models": models,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "query": query,
        "free_only": free_only,
    }
    return render(request, "watchlist/model_list.html", context)


def model_detail(request, model_id):
    """Страница /models/<id>/: текущий статус, провайдеры и история.

    Статус запрашивается у OpenRouter при открытии страницы, но в историю
    не записывается: GET-запрос не должен изменять данные приложения.
    """
    model = fetch_one(MODEL_SQL, [model_id])
    context = {"model": model, "model_id": model_id}

    if model is not None:
        ai_model = AIModel(model["openrouter_id"], model["name"])
        result = CheckResult.from_providers(
            ai_model, fetch_providers(ai_model.id)
        )
        context.update({
            "result": result,
            "working": count_working(result.providers),
            "summary": fetch_one(
                MODEL_SUMMARY_SQL, [STATUS_AVAILABLE, model_id]
            ),
            "history": fetch_all(MODEL_HISTORY_SQL, [model_id, HISTORY_LIMIT]),
        })

    return render(
        request,
        "watchlist/model_detail.html",
        context,
        status=404 if model is None else 200,
    )
