"""Подключение к базе данных SQLite и выполнение запросов."""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "aimonitor.sqlite"
SCHEMA_FILE = BASE_DIR / "sql" / "schema.sql"


def get_connection(path: str | Path | None = None) -> sqlite3.Connection:
    """Открыть соединение и включить проверку внешних ключей.

    По умолчанию SQLite не проверяет, что внешний ключ ссылается
    на существующую запись, поэтому PRAGMA выполняется при каждом
    подключении.
    """
    conn = sqlite3.connect(path or DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Создать таблицы командами из sql/schema.sql."""
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))


def fetch_all(sql: str, params=()) -> list[sqlite3.Row]:
    """Выполнить SELECT и вернуть все строки.

    Значения передаются отдельно от текста запроса (параметры ? или
    :имя). Благодаря sqlite3.Row к полям строки можно обращаться
    по имени: row["name"] в Python и {{ row.name }} в шаблоне.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def fetch_one(sql: str, params=()) -> sqlite3.Row | None:
    """Выполнить SELECT и вернуть первую строку или None."""
    rows = fetch_all(sql, params)
    return rows[0] if rows else None
