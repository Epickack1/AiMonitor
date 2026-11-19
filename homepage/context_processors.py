"""Контекстный процессор: общие данные для всех шаблонов.

Функция вызывается при отрисовке каждого шаблона с RequestContext
(render()), поэтому название сайта и число моделей не нужно
передавать в context каждого представления.
"""

from django.db import DatabaseError

from watchlist.models import AIModel

SITE_NAME = "AIMonitor"


def site(request) -> dict:
    """Название сайта и число отслеживаемых моделей.

    Если таблицы ещё не созданы (не выполнена команда migrate),
    запрос к базе вызывает DatabaseError: страница всё равно
    открывается, а вместо числа выводится None.
    """
    try:
        tracked = AIModel.objects.filter(is_tracked=True).count()
    except DatabaseError:
        tracked = None
    return {"site_name": SITE_NAME, "tracked_models_count": tracked}
