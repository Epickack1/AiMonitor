"""Перенос списка отслеживания и истории проверок из JSON в SQLite.

Запуск из корня проекта: python -m db.import_json

JSON читается функциями storage.py из ПР3, поэтому некорректные записи
пропускаются так же, как в консольной версии. Перед импортом таблицы
очищаются: скрипт можно запускать повторно, например после новых
проверок в консольной версии.
"""

import sqlite3

from db.database import DB_PATH, create_schema, get_connection
from models import AIModel, CheckResult
from storage import DATA_FILE, HISTORY_FILE, load_history, load_watchlist


def vendor_of(model: AIModel) -> tuple[str, str]:
    """Slug и название разработчика модели.

    Slug — часть id до «/», название — часть названия модели до «: »,
    например «OpenAI» из «OpenAI: GPT-4o-mini».
    """
    slug = model.id.partition("/")[0]
    name, sep, _ = model.name.partition(": ")
    return slug, name if sep else slug


def import_vendors(conn: sqlite3.Connection, models: list[AIModel]) -> dict:
    """Добавить разработчиков, вернуть словарь slug → id записи."""
    vendors = {}
    for model in models:
        slug, name = vendor_of(model)
        vendors.setdefault(slug, name)
    conn.executemany(
        "INSERT INTO vendors (id, slug, name) VALUES (?, ?, ?)",
        [
            (number, slug, name)
            for number, (slug, name) in enumerate(vendors.items(), start=1)
        ],
    )
    return {slug: number for number, slug in enumerate(vendors, start=1)}


def import_models(
    conn: sqlite3.Connection,
    models: list[AIModel],
    tracked: set[str],
    vendor_ids: dict,
) -> dict:
    """Добавить модели, вернуть словарь id OpenRouter → id записи."""
    conn.executemany(
        """
        INSERT INTO models (id, openrouter_id, name, vendor_id, is_tracked)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                number,
                model.id,
                model.name,
                vendor_ids[vendor_of(model)[0]],
                int(model.id in tracked),
            )
            for number, model in enumerate(models, start=1)
        ],
    )
    return {model.id: number for number, model in enumerate(models, start=1)}


def import_checks(
    conn: sqlite3.Connection, history: list[CheckResult], model_ids: dict
) -> None:
    """Добавить результаты проверок."""
    conn.executemany(
        """
        INSERT INTO checks (id, model_id, status, uptime, checked_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                number,
                model_ids[result.model.id],
                result.status,
                result.uptime,
                result.checked_at,
            )
            for number, result in enumerate(history, start=1)
        ],
    )


def main(
    watchlist_file: str = DATA_FILE,
    history_file: str = HISTORY_FILE,
    db_path=DB_PATH,
) -> tuple[int, int]:
    """Перенести данные. Возвращает число моделей и проверок."""
    watchlist = load_watchlist(watchlist_file)
    history = load_history(watchlist, history_file)

    # Модели из истории, которых уже нет в списке отслеживания,
    # тоже попадают в таблицу models: на них ссылаются проверки.
    models = list(watchlist)
    known = {model.id for model in watchlist}
    for result in history:
        if result.model.id not in known:
            known.add(result.model.id)
            models.append(result.model)

    conn = get_connection(db_path)
    try:
        create_schema(conn)
        conn.execute("DELETE FROM checks")
        conn.execute("DELETE FROM models")
        conn.execute("DELETE FROM vendors")
        vendor_ids = import_vendors(conn, models)
        tracked = {model.id for model in watchlist}
        model_ids = import_models(conn, models, tracked, vendor_ids)
        import_checks(conn, history, model_ids)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return len(models), len(history)


if __name__ == "__main__":
    models_count, checks_count = main()
    print(f"Перенесено моделей: {models_count}, проверок: {checks_count}")
