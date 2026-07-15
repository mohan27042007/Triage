"""Small SQLite persistence layer for the local-first Triage prototype."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

DATABASE_PATH = Path(__file__).with_name("triage.db")


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                deadline TEXT,
                mandatory INTEGER,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open'
            )
            """
        )


def create_item(text: str, classification: dict[str, Any]) -> dict[str, Any]:
    """Persist one classified item and return the stored record."""
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO items (text, category, reason, deadline, mandatory, source, created_at, status)
            VALUES (?, ?, ?, ?, ?, 'manual', ?, 'open')
            """,
            (
                text.strip(),
                classification["category"],
                classification["reason"],
                classification["deadline"],
                classification["mandatory"],
                created_at,
            ),
        )
        item_id = cursor.lastrowid
    return get_item(item_id)


def get_item(item_id: int) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def get_open_obligations() -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM items
            WHERE category = 'Obligation' AND status = 'open'
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def mark_done(item_id: int) -> bool:
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE items SET status = 'done' WHERE id = ? AND status = 'open'", (item_id,)
        )
    return cursor.rowcount == 1


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["mandatory"] = None if item["mandatory"] is None else bool(item["mandatory"])
    return item
