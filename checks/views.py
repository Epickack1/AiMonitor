"""Страницы истории проверок и статистики доступности моделей.

Данные читаются из SQLite (data/aimonitor.sqlite) SQL-запросами.
"""

from django.shortcuts import render

from db.database import fetch_all, fetch_one
from models.provider import STATUS_AVAILABLE

HISTORY_LIMIT = 100

# Необязательные фильтры: пустая строка в параметре отключает условие.
HISTORY_FILTER = """
    WHERE (:day = '' OR substr(checks.checked_at, 1, 10) = :day)
      AND (:status = '' OR checks.status = :status)
"""

HISTORY_SQL = """
    SELECT
        checks.checked_at,
        checks.status,
        checks.uptime,
        models.openrouter_id,
        models.name AS model_name
    FROM checks
    JOIN models
        ON checks.model_id = models.id
""" + HISTORY_FILTER + """
    ORDER BY checks.id DESC
    LIMIT :limit
"""

HISTORY_COUNT_SQL = """
    SELECT COUNT(*) AS checks_count
    FROM checks
""" + HISTORY_FILTER

DAYS_SQL = """
    SELECT DISTINCT substr(checked_at, 1, 10) AS day
    FROM checks
    ORDER BY day DESC
"""

STATUS_COUNTS_SQL = """
    SELECT
        status,
        COUNT(*) AS checks_count
    FROM checks
    GROUP BY status
    ORDER BY checks_count DESC
"""

MODEL_STATS_SQL = """
    SELECT
        models.openrouter_id,
        models.name,
        COUNT(checks.id) AS checks_count,
        ROUND(100.0 * SUM(checks.status = ?) / COUNT(checks.id), 1)
            AS percent,
        AVG(checks.uptime) AS avg_uptime
    FROM models
    JOIN checks
        ON checks.model_id = models.id
    GROUP BY models.id, models.openrouter_id, models.name
    ORDER BY percent DESC, COALESCE(avg_uptime, 0) DESC, models.openrouter_id
"""

PROBLEM_MODELS_SQL = """
    SELECT
        models.openrouter_id,
        models.name,
        COUNT(checks.id) AS checks_count,
        COUNT(checks.id) - SUM(checks.status = ?) AS failed_count
    FROM models
    JOIN checks
        ON checks.model_id = models.id
    GROUP BY models.id, models.openrouter_id, models.name
    HAVING SUM(checks.status = ?) < COUNT(checks.id)
    ORDER BY failed_count DESC, models.openrouter_id
"""

VENDOR_STATS_SQL = """
    SELECT
        vendors.name AS vendor_name,
        COUNT(DISTINCT models.id) AS models_count,
        COUNT(checks.id) AS checks_count
    FROM vendors
    JOIN models
        ON models.vendor_id = vendors.id
    LEFT JOIN checks
        ON checks.model_id = models.id
    WHERE models.is_tracked = 1
    GROUP BY vendors.id, vendors.name
    ORDER BY models_count DESC, vendor_name
"""


def history(request):
    """Страница /checks/: проверки за выбранный день и с выбранным статусом.

    Значения из адреса /checks/?day=...&status=... передаются в запрос
    параметрами, поэтому не могут изменить его текст.
    """
    filters = {
        "day": request.GET.get("day", ""),
        "status": request.GET.get("status", ""),
    }
    context = {
        "results": fetch_all(HISTORY_SQL, {**filters, "limit": HISTORY_LIMIT}),
        "total": fetch_one(HISTORY_COUNT_SQL, filters)["checks_count"],
        "days": fetch_all(DAYS_SQL),
        "statuses": fetch_all(STATUS_COUNTS_SQL),
        **filters,
    }
    return render(request, "checks/history.html", context)


def stats(request):
    """Страница /checks/stats/: статистика доступности по истории."""
    model_stats = fetch_all(MODEL_STATS_SQL, [STATUS_AVAILABLE])
    context = {
        "model_stats": model_stats,
        "total": sum(item["checks_count"] for item in model_stats),
        "problem_models": fetch_all(
            PROBLEM_MODELS_SQL, [STATUS_AVAILABLE, STATUS_AVAILABLE]
        ),
        "status_counts": fetch_all(STATUS_COUNTS_SQL),
        "vendors": fetch_all(VENDOR_STATS_SQL),
    }
    return render(request, "checks/stats.html", context)
