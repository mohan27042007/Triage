"""Small SQLite persistence layer for the local-first Triage prototype."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATABASE_PATH = Path(__file__).with_name("triage.db")


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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
                status TEXT NOT NULL DEFAULT 'open',
                archived_path TEXT,
                source_id TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS study_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                weight INTEGER NOT NULL,
                subtopics TEXT NOT NULL,
                created_at TEXT NOT NULL,
                question_bank_archived_path TEXT,
                unit_notes_archived_path TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS assignment_help (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL,
                requirements TEXT NOT NULL,
                concepts TEXT NOT NULL,
                approach TEXT NOT NULL,
                test_cases TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        _add_column_if_missing(connection, "items", "archived_path", "TEXT")
        _add_column_if_missing(connection, "items", "source_id", "TEXT")
        _add_column_if_missing(connection, "study_plans", "question_bank_archived_path", "TEXT")
        _add_column_if_missing(connection, "study_plans", "unit_notes_archived_path", "TEXT")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_source_id "
            "ON items(source_id) WHERE source_id IS NOT NULL"
        )


def _add_column_if_missing(
    connection: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    """Apply a small additive migration for existing local databases."""
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_item(
    text: str,
    classification: dict[str, Any],
    archived_path: str | None = None,
    source: str = "manual",
    source_id: str | None = None,
) -> dict[str, Any] | None:
    """Persist one classified item and return the stored record."""
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO items (
                text, category, reason, deadline, mandatory, source,
                created_at, status, archived_path, source_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                text.strip(),
                classification["category"],
                classification["reason"],
                classification["deadline"],
                classification["mandatory"],
                source,
                created_at,
                archived_path,
                source_id,
            ),
        )
        item_id = cursor.lastrowid
    return get_item(item_id) if item_id else None


def get_item(item_id: int) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def get_item_by_source_id(source_id: str) -> dict[str, Any] | None:
    """Return one previously imported source item, if it exists."""
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM items WHERE source_id = ?", (source_id,)
        ).fetchone()
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


def create_pending_action(
    item_id: int, action_type: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Create one pending action, or reuse an identical action awaiting review."""
    with _connection() as connection:
        existing = connection.execute(
            """
            SELECT * FROM pending_actions
            WHERE item_id = ? AND action_type = ? AND status = 'pending'
            """,
            (item_id, action_type),
        ).fetchone()
        if existing:
            return _row_to_pending_action(existing)

        cursor = connection.execute(
            """
            INSERT INTO pending_actions (item_id, action_type, payload, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (item_id, action_type, json.dumps(payload), datetime.now().astimezone().isoformat()),
        )
        row = connection.execute(
            "SELECT * FROM pending_actions WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _row_to_pending_action(row)


def get_pending_actions() -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT pending_actions.*, items.text AS item_text
            FROM pending_actions
            JOIN items ON items.id = pending_actions.item_id
            WHERE pending_actions.status = 'pending'
            ORDER BY pending_actions.created_at ASC
            """
        ).fetchall()
    return [_row_to_pending_action(row) for row in rows]


def approve_pending_action(action_id: int) -> dict[str, Any] | None:
    """Apply a pending action exactly once and record its approval."""
    with _connection() as connection:
        action = connection.execute(
            "SELECT * FROM pending_actions WHERE id = ? AND status = 'pending'", (action_id,)
        ).fetchone()
        if not action:
            return None
        if action["action_type"] != "mark_done":
            raise ValueError(f"Unsupported pending action: {action['action_type']}")

        completed = connection.execute(
            "UPDATE items SET status = 'done' WHERE id = ? AND status = 'open'", (action["item_id"],)
        )
        if completed.rowcount != 1:
            return None
        connection.execute(
            "UPDATE pending_actions SET status = 'approved' WHERE id = ?", (action_id,)
        )
        updated = connection.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,)).fetchone()
    return _row_to_pending_action(updated)


def reject_pending_action(action_id: int) -> dict[str, Any] | None:
    """Reject a pending action without applying its underlying change."""
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE pending_actions SET status = 'rejected' WHERE id = ? AND status = 'pending'",
            (action_id,),
        )
        if cursor.rowcount != 1:
            return None
        updated = connection.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,)).fetchone()
    return _row_to_pending_action(updated)


def replace_study_plan(
    topics: list[dict[str, Any]],
    question_bank_archived_path: str | None = None,
    unit_notes_archived_path: str | None = None,
) -> list[dict[str, Any]]:
    """Store the latest study plan, replacing the previous local plan."""
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        connection.execute("DELETE FROM study_plans")
        connection.executemany(
            """
            INSERT INTO study_plans (
                topic, weight, subtopics, created_at,
                question_bank_archived_path, unit_notes_archived_path
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    topic["topic"],
                    topic["weight"],
                    json.dumps(topic["subtopics"]),
                    created_at,
                    question_bank_archived_path,
                    unit_notes_archived_path,
                )
                for topic in topics
            ],
        )
    return get_study_plan()


def get_study_plan() -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM study_plans ORDER BY weight DESC, id ASC"
        ).fetchall()
    return [
        {
            "id": row["id"],
            "topic": row["topic"],
            "weight": row["weight"],
            "subtopics": json.loads(row["subtopics"]),
            "created_at": row["created_at"],
            "question_bank_archived_path": row["question_bank_archived_path"],
            "unit_notes_archived_path": row["unit_notes_archived_path"],
        }
        for row in rows
    ]


def create_assignment_help(prompt: str, scaffold: dict[str, Any]) -> dict[str, Any] | None:
    """Persist one assignment scaffold and return its stored record."""
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO assignment_help (prompt, requirements, concepts, approach, test_cases, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                prompt.strip(),
                json.dumps(scaffold["requirements"]),
                json.dumps(scaffold["concepts"]),
                json.dumps(scaffold["approach"]),
                json.dumps(scaffold["test_cases"]),
                created_at,
            ),
        )
        row = connection.execute(
            "SELECT * FROM assignment_help WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _row_to_assignment_help(row) if row else None


def get_assignment_history() -> list[dict[str, Any]]:
    """Return saved assignment scaffolds with the newest first."""
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM assignment_help ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_row_to_assignment_help(row) for row in rows]


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["mandatory"] = None if item["mandatory"] is None else bool(item["mandatory"])
    return item


def _row_to_pending_action(row: sqlite3.Row) -> dict[str, Any]:
    action = dict(row)
    action["payload"] = json.loads(action["payload"])
    return action


def _row_to_assignment_help(row: sqlite3.Row) -> dict[str, Any]:
    scaffold = dict(row)
    scaffold["requirements"] = json.loads(scaffold["requirements"])
    scaffold["concepts"] = json.loads(scaffold["concepts"])
    scaffold["approach"] = json.loads(scaffold["approach"])
    scaffold["test_cases"] = json.loads(scaffold["test_cases"])
    return scaffold
