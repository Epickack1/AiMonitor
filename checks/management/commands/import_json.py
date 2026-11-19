"""Перенос списка отслеживания и истории проверок из JSON в модели Django.

Запуск: python manage.py import_json

То же, что db/import_json.py из ПР7, но через ORM: данные попадают
в таблицы Django-моделей в db.sqlite3. Перед импортом записи удаляются,
поэтому команду можно запускать повторно.
"""

from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from checks.models import STATUS_BY_LABEL, Check
from db.import_json import vendor_of
from models.check import TIME_FORMAT
from storage import DATA_FILE, HISTORY_FILE, load_history, load_watchlist
from watchlist.models import AIModel, Vendor


def parse_time(text: str) -> datetime:
    """Время из JSON ('2026-09-26 01:29') в часовом поясе TIME_ZONE."""
    return timezone.make_aware(datetime.strptime(text, TIME_FORMAT))


@transaction.atomic
def import_data(
    watchlist_file: str = DATA_FILE, history_file: str = HISTORY_FILE
) -> tuple[int, int]:
    """Перенести данные. Возвращает число моделей и проверок.

    Порядок важен: сначала разработчики, затем модели, затем проверки —
    запись с внешним ключом может ссылаться только на существующую.
    Удаление идёт в обратном порядке.
    """
    watchlist = load_watchlist(watchlist_file)
    history = load_history(watchlist, history_file)
    tracked = {model.id for model in watchlist}

    # Модели из истории, которых нет в списке отслеживания, тоже нужны:
    # на них ссылаются проверки.
    models = list(watchlist)
    known = set(tracked)
    for result in history:
        if result.model.id not in known:
            known.add(result.model.id)
            models.append(result.model)

    Check.objects.all().delete()
    AIModel.objects.all().delete()
    Vendor.objects.all().delete()

    vendors = {}
    for model in models:
        slug, name = vendor_of(model)
        if slug not in vendors:
            vendors[slug] = Vendor.objects.create(slug=slug, name=name)

    ai_models = {
        model.id: AIModel.objects.create(
            openrouter_id=model.id,
            name=model.name,
            vendor=vendors[vendor_of(model)[0]],
            is_tracked=model.id in tracked,
        )
        for model in models
    }

    Check.objects.bulk_create(
        Check(
            model=ai_models[result.model.id],
            status=STATUS_BY_LABEL[result.status],
            uptime=result.uptime,
            checked_at=parse_time(result.checked_at),
        )
        for result in history
    )
    return len(models), len(history)


class Command(BaseCommand):
    help = "Перенести watchlist.json и history.json в модели Django"

    def handle(self, *args, **options):
        models_count, checks_count = import_data()
        self.stdout.write(
            f"Перенесено моделей: {models_count}, проверок: {checks_count}"
        )
