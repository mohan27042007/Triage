"""Small SQLite persistence layer for the local-first Triage prototype."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATABASE_PATH = Path(__file__).with_name("triage.db")
VALID_ITEM_SOURCES = {"manual", "gmail", "classroom", "whatsapp-demo"}


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
                attachments TEXT NOT NULL DEFAULT '[]',
                source_id TEXT,
                is_poll_or_form INTEGER NOT NULL DEFAULT 0
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
        _add_column_if_missing(connection, "items", "attachments", "TEXT NOT NULL DEFAULT '[]'")
        _add_column_if_missing(connection, "items", "source_id", "TEXT")
        _add_column_if_missing(connection, "items", "is_poll_or_form", "INTEGER NOT NULL DEFAULT 0")
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
    attachments: list[dict[str, Any]] | None = None,
    source: str = "manual",
    source_id: str | None = None,
) -> dict[str, Any] | None:
    """Persist one classified item and return the stored record."""
    if source not in VALID_ITEM_SOURCES:
        raise ValueError(f"Unsupported item source: {source}")
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO items (
                text, category, reason, deadline, mandatory, source,
                created_at, status, archived_path, attachments, source_id, is_poll_or_form
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
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
                json.dumps(attachments or []),
                source_id,
                bool(classification.get("is_poll_or_form", False)),
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


def has_items_from_source(source: str) -> bool:
    """Return whether any persisted items came from one known source."""
    if source not in VALID_ITEM_SOURCES:
        raise ValueError(f"Unsupported item source: {source}")
    with _connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM items WHERE source = ? LIMIT 1", (source,)
        ).fetchone()
    return row is not None


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


def get_recent_items(limit: int = 60) -> list[dict[str, Any]]:
    """Return the newest classified items from every supported source."""
    if not 1 <= limit <= 100:
        raise ValueError("Stream limit must be between 1 and 100.")
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM items ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def get_archived_attachments() -> list[dict[str, Any]]:
    """Return metadata for locally archived source and upload files, newest first."""
    entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT text, source, created_at, archived_path, attachments
            FROM items
            WHERE archived_path IS NOT NULL OR attachments != '[]'
            ORDER BY created_at DESC
            """
        ).fetchall()
        study_rows = connection.execute(
            """
            SELECT created_at, question_bank_archived_path, unit_notes_archived_path
            FROM study_plans
            WHERE question_bank_archived_path IS NOT NULL OR unit_notes_archived_path IS NOT NULL
            ORDER BY created_at DESC
            """
        ).fetchall()

    for row in rows:
        for attachment in json.loads(row["attachments"] or "[]"):
            archived_path = attachment.get("archived_path")
            if not archived_path or archived_path in seen_paths:
                continue
            seen_paths.add(archived_path)
            entries.append(
                {
                    "archived_path": archived_path,
                    "filename": attachment.get("filename") or archived_path,
                    "mime_type": attachment.get("mime_type") or "application/octet-stream",
                    "size": attachment.get("size"),
                    "source": row["source"],
                    "item_text": row["text"],
                    "created_at": row["created_at"],
                }
            )
        if row["archived_path"] and row["archived_path"] not in seen_paths:
            seen_paths.add(row["archived_path"])
            entries.append(
                {
                    "archived_path": row["archived_path"],
                    "filename": row["archived_path"],
                    "mime_type": "text/plain",
                    "size": None,
                    "source": row["source"],
                    "item_text": row["text"],
                    "created_at": row["created_at"],
                }
            )

    for row in study_rows:
        for label, archived_path in (
            ("Question bank", row["question_bank_archived_path"]),
            ("Unit notes", row["unit_notes_archived_path"]),
        ):
            if not archived_path or archived_path in seen_paths:
                continue
            seen_paths.add(archived_path)
            entries.append(
                {
                    "archived_path": archived_path,
                    "filename": archived_path,
                    "mime_type": "text/plain",
                    "size": None,
                    "source": "study upload",
                    "item_text": label,
                    "created_at": row["created_at"],
                }
            )
    return entries


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
            if action_type == "prepare_form_draft":
                connection.execute(
                    "UPDATE pending_actions SET payload = ? WHERE id = ?",
                    (json.dumps(payload), existing["id"]),
                )
                existing = connection.execute(
                    "SELECT * FROM pending_actions WHERE id = ?", (existing["id"],)
                ).fetchone()
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
        if action["action_type"] == "prepare_form_draft":
            connection.execute(
                "UPDATE pending_actions SET status = 'approved' WHERE id = ?", (action_id,)
            )
            updated = connection.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,)).fetchone()
            return _row_to_pending_action(updated)
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
    item["is_poll_or_form"] = bool(item.get("is_poll_or_form", False))
    item["attachments"] = json.loads(item.get("attachments") or "[]")
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
