"""Перенос данных из базы ПР7 (data/aimonitor.sqlite) в модели Django.

Запуск: python manage.py import_pr7 [--source путь]

База ПР7 не изменяется: она только читается. Записи переносятся
с прежними id, поэтому внешние ключи указывают на те же записи,
что и в ПР7. Перед переносом таблицы Django очищаются, поэтому
команду можно запускать повторно. После переноса число записей
в каждой таблице сравнивается с исходным.
"""

import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from checks.management.commands.import_json import parse_time
from checks.models import Check
from db.database import DB_PATH, get_connection
from watchlist.models import AIModel, Vendor


def read_rows(source: Path) -> dict[str, list[sqlite3.Row]]:
    """Прочитать три таблицы ПР7 целиком."""
    if not Path(source).exists():
        raise CommandError(f"Нет базы ПР7: {source}")
    conn = get_connection(source)
    conn.row_factory = sqlite3.Row
    try:
        return {
            table: conn.execute(
                f"SELECT * FROM {table} ORDER BY id"
            ).fetchall()
            for table in ("vendors", "models", "checks")
        }
    finally:
        conn.close()


@transaction.atomic
def import_pr7(source: Path = DB_PATH) -> tuple[int, int, int]:
    """Перенести данные. Возвращает число разработчиков, моделей, проверок.

    Сначала создаются записи, на которые ссылаются внешние ключи:
    разработчики, затем модели, затем проверки. Удаление — в обратном
    порядке, иначе PROTECT у AIModel.vendor запретит удалить разработчика.
    """
    rows = read_rows(source)

    Check.objects.all().delete()
    AIModel.objects.all().delete()
    Vendor.objects.all().delete()

    Vendor.objects.bulk_create(
        Vendor(id=row["id"], slug=row["slug"], name=row["name"])
        for row in rows["vendors"]
    )
    AIModel.objects.bulk_create(
        AIModel(
            id=row["id"],
            openrouter_id=row["openrouter_id"],
            name=row["name"],
            vendor_id=row["vendor_id"],
            is_tracked=bool(row["is_tracked"]),
        )
        for row in rows["models"]
    )
    Check.objects.bulk_create(
        Check(
            id=row["id"],
            model_id=row["model_id"],
            status=row["status"],
            uptime=row["uptime"],
            checked_at=parse_time(row["checked_at"]),
        )
        for row in rows["checks"]
    )

    counts = (
        Vendor.objects.count(),
        AIModel.objects.count(),
        Check.objects.count(),
    )
    expected = tuple(len(rows[table]) for table in rows)
    if counts != expected:
        raise CommandError(
            f"Перенесено {counts}, а в базе ПР7 {expected} записей"
        )
    return counts


class Command(BaseCommand):
    help = "Перенести разработчиков, модели и проверки из базы ПР7"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", type=Path, default=DB_PATH,
            help="файл базы ПР7 (по умолчанию data/aimonitor.sqlite)",
        )

    def handle(self, *args, **options):
        vendors, models, checks = import_pr7(options["source"])
        self.stdout.write(
            f"Перенесено разработчиков: {vendors}, моделей: {models}, "
            f"проверок: {checks}"
        )
