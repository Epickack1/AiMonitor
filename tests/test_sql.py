"""Тесты SQL-слоя ПР7: перенос JSON в SQLite скриптом db/import_json.py.

Временная база создаётся из тестовых JSON-файлов, поэтому тесты
не зависят от данных проекта.
"""

import sqlite3

import pytest

import db.database
from db.import_json import main as import_json
from models import AIModel, CheckResult
from models.provider import STATUS_AVAILABLE, STATUS_DOWN
from storage import save_history, save_watchlist


@pytest.fixture
def database(tmp_path):
    """Временная база SQLite, заполненная из JSON скриптом импорта."""
    gpt = AIModel("openai/gpt-4o-mini", "OpenAI: GPT-4o-mini")
    gemma = AIModel("google/gemma:free", "Google: Gemma (free)")
    removed = AIModel("old/model", "old/model")
    save_watchlist([gpt, gemma], tmp_path / "watchlist.json")
    save_history(
        [
            CheckResult(removed, STATUS_AVAILABLE, 90.0, "2026-09-25 09:00"),
            CheckResult(gpt, STATUS_AVAILABLE, 99.0, "2026-09-26 10:00"),
            CheckResult(gemma, STATUS_DOWN, None, "2026-09-26 10:00"),
            CheckResult(gpt, STATUS_AVAILABLE, 100.0, "2026-09-27 11:00"),
        ],
        tmp_path / "history.json",
    )
    db_file = tmp_path / "test.sqlite"
    import_json(
        tmp_path / "watchlist.json", tmp_path / "history.json", db_file
    )
    return db_file


def test_import_json(database):
    conn = db.database.get_connection(database)
    counts = [
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("vendors", "models", "checks")
    ]
    tracked = conn.execute(
        "SELECT openrouter_id FROM models WHERE is_tracked = 0"
    ).fetchall()
    conn.close()
    assert counts == [3, 3, 4]
    assert tracked == [("old/model",)]


def test_import_json_can_be_repeated(database, tmp_path):
    assert import_json(
        tmp_path / "watchlist.json", tmp_path / "history.json", database
    ) == (3, 4)


def test_foreign_keys_are_checked(database):
    conn = db.database.get_connection(database)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO checks (model_id, status, checked_at)"
            " VALUES (999, 'x', '2026-01-01 00:00')"
        )
    conn.close()
