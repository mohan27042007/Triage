"""User-scoped persistence for local SQLite and hosted PostgreSQL deployments."""

import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATABASE_PATH = Path(__file__).with_name("triage.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USING_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
DEFAULT_OWNER_ID = "local-demo"
VALID_ITEM_SOURCES = {"manual", "gmail", "classroom", "whatsapp-demo"}


class _PostgresConnection:
    """Translate this small prototype's SQLite-style placeholders for psycopg."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._connection.__exit__(*args)

    def execute(self, query: str, parameters: object = ()):
        return self._connection.execute(query.replace("?", "%s"), parameters)

    def executemany(self, query: str, parameters: object):
        return self._connection.executemany(query.replace("?", "%s"), parameters)


def _connection():
    if USING_POSTGRES:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires psycopg.") from exc
        return _PostgresConnection(psycopg.connect(DATABASE_URL, row_factory=dict_row))
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    if USING_POSTGRES:
        _initialize_postgres_database()
        return
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
                is_poll_or_form INTEGER NOT NULL DEFAULT 0,
                owner_id TEXT NOT NULL DEFAULT 'local-demo'
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
                unit_notes_archived_path TEXT,
                owner_id TEXT NOT NULL DEFAULT 'local-demo'
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
                owner_id TEXT NOT NULL DEFAULT 'local-demo',
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
                created_at TEXT NOT NULL,
                owner_id TEXT NOT NULL DEFAULT 'local-demo'
            )
            """
        )
        _add_column_if_missing(connection, "items", "archived_path", "TEXT")
        _add_column_if_missing(connection, "items", "attachments", "TEXT NOT NULL DEFAULT '[]'")
        _add_column_if_missing(connection, "items", "source_id", "TEXT")
        _add_column_if_missing(connection, "items", "is_poll_or_form", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(connection, "items", "owner_id", "TEXT NOT NULL DEFAULT 'local-demo'")
        _add_column_if_missing(connection, "study_plans", "question_bank_archived_path", "TEXT")
        _add_column_if_missing(connection, "study_plans", "unit_notes_archived_path", "TEXT")
        _add_column_if_missing(connection, "study_plans", "owner_id", "TEXT NOT NULL DEFAULT 'local-demo'")
        _add_column_if_missing(connection, "pending_actions", "owner_id", "TEXT NOT NULL DEFAULT 'local-demo'")
        _add_column_if_missing(connection, "assignment_help", "owner_id", "TEXT NOT NULL DEFAULT 'local-demo'")
        connection.execute("DROP INDEX IF EXISTS idx_items_source_id")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_owner_source_id "
            "ON items(owner_id, source_id) WHERE source_id IS NOT NULL"
        )


def _initialize_postgres_database() -> None:
    """Create the hosted schema without modifying any local SQLite data."""
    with _connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id BIGSERIAL PRIMARY KEY, text TEXT NOT NULL, category TEXT NOT NULL,
                reason TEXT NOT NULL, deadline TEXT, mandatory BOOLEAN, source TEXT NOT NULL,
                created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', archived_path TEXT,
                attachments TEXT NOT NULL DEFAULT '[]', source_id TEXT, is_poll_or_form BOOLEAN NOT NULL DEFAULT FALSE,
                owner_id TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS study_plans (
                id BIGSERIAL PRIMARY KEY, topic TEXT NOT NULL, weight INTEGER NOT NULL,
                subtopics TEXT NOT NULL, created_at TEXT NOT NULL, question_bank_archived_path TEXT,
                unit_notes_archived_path TEXT, owner_id TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS pending_actions (
                id BIGSERIAL PRIMARY KEY, item_id BIGINT NOT NULL REFERENCES items(id),
                action_type TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL, owner_id TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS assignment_help (
                id BIGSERIAL PRIMARY KEY, prompt TEXT NOT NULL, requirements TEXT NOT NULL,
                concepts TEXT NOT NULL, approach TEXT NOT NULL, test_cases TEXT NOT NULL,
                created_at TEXT NOT NULL, owner_id TEXT NOT NULL
            )
        """)
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_items_owner_source_id ON items(owner_id, source_id) WHERE source_id IS NOT NULL")


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
    owner_id: str = DEFAULT_OWNER_ID,
) -> dict[str, Any] | None:
    """Persist one classified item and return the stored record."""
    if source not in VALID_ITEM_SOURCES:
        raise ValueError(f"Unsupported item source: {source}")
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        insert_query = """
            INSERT INTO items (
                text, category, reason, deadline, mandatory, source,
                created_at, status, archived_path, attachments, source_id, is_poll_or_form, owner_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
        """
        cursor = connection.execute(
            f"{insert_query} RETURNING id" if USING_POSTGRES else insert_query,
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
                owner_id,
            ),
        )
        item_id = cursor.fetchone()["id"] if USING_POSTGRES else cursor.lastrowid
    return get_item(item_id, owner_id) if item_id else None


def get_item(item_id: int, owner_id: str = DEFAULT_OWNER_ID) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute("SELECT * FROM items WHERE id = ? AND owner_id = ?", (item_id, owner_id)).fetchone()
    return _row_to_item(row) if row else None


def get_item_by_source_id(source_id: str, owner_id: str = DEFAULT_OWNER_ID) -> dict[str, Any] | None:
    """Return one previously imported source item, if it exists."""
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM items WHERE source_id = ? AND owner_id = ?", (source_id, owner_id)
        ).fetchone()
    return _row_to_item(row) if row else None


def has_items_from_source(source: str, owner_id: str = DEFAULT_OWNER_ID) -> bool:
    """Return whether any persisted items came from one known source."""
    if source not in VALID_ITEM_SOURCES:
        raise ValueError(f"Unsupported item source: {source}")
    with _connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM items WHERE source = ? AND owner_id = ? LIMIT 1", (source, owner_id)
        ).fetchone()
    return row is not None


def get_open_obligations(owner_id: str = DEFAULT_OWNER_ID) -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM items
            WHERE category = 'Obligation' AND status = 'open' AND owner_id = ?
            ORDER BY created_at DESC
            """, (owner_id,)
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def get_recent_items(limit: int = 60, owner_id: str = DEFAULT_OWNER_ID) -> list[dict[str, Any]]:
    """Return the newest classified items from every supported source."""
    if not 1 <= limit <= 100:
        raise ValueError("Stream limit must be between 1 and 100.")
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM items WHERE owner_id = ? ORDER BY created_at DESC, id DESC LIMIT ?", (owner_id, limit)
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def get_history_items(
    query: str = "", category: str = "", source: str = "", status: str = "", limit: int = 100,
    owner_id: str = DEFAULT_OWNER_ID,
) -> list[dict[str, Any]]:
    """Search the locally stored item history using safe, optional filters."""
    if not 1 <= limit <= 100:
        raise ValueError("History limit must be between 1 and 100.")
    allowed_categories = {"Obligation", "Study Material", "Noise"}
    allowed_sources = VALID_ITEM_SOURCES
    allowed_statuses = {"open", "done"}
    clauses: list[str] = ["owner_id = ?"]
    parameters: list[Any] = [owner_id]
    if query.strip():
        operator = "ILIKE" if USING_POSTGRES else "LIKE"
        collation = "" if USING_POSTGRES else " COLLATE NOCASE"
        clauses.append(f"(text {operator} ?{collation} OR reason {operator} ?{collation})")
        search_term = f"%{query.strip()}%"
        parameters.extend([search_term, search_term])
    if category in allowed_categories:
        clauses.append("category = ?")
        parameters.append(category)
    if source in allowed_sources:
        clauses.append("source = ?")
        parameters.append(source)
    if status in allowed_statuses:
        clauses.append("status = ?")
        parameters.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM items {where} ORDER BY created_at DESC, id DESC LIMIT ?",
            [*parameters, limit],
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def get_archived_attachments(owner_id: str = DEFAULT_OWNER_ID) -> list[dict[str, Any]]:
    """Return metadata for locally archived source and upload files, newest first."""
    entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT text, source, created_at, archived_path, attachments
            FROM items
            WHERE owner_id = ? AND (archived_path IS NOT NULL OR attachments != '[]')
            ORDER BY created_at DESC
            """, (owner_id,)
        ).fetchall()
        study_rows = connection.execute(
            """
            SELECT created_at, question_bank_archived_path, unit_notes_archived_path
            FROM study_plans
            WHERE owner_id = ? AND (question_bank_archived_path IS NOT NULL OR unit_notes_archived_path IS NOT NULL)
            ORDER BY created_at DESC
            """, (owner_id,)
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


def mark_done(item_id: int, owner_id: str = DEFAULT_OWNER_ID) -> bool:
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE items SET status = 'done' WHERE id = ? AND status = 'open' AND owner_id = ?", (item_id, owner_id)
        )
    return cursor.rowcount == 1


def create_pending_action(
    item_id: int, action_type: str, payload: dict[str, Any], owner_id: str = DEFAULT_OWNER_ID
) -> dict[str, Any]:
    """Create one pending action, or reuse an identical action awaiting review."""
    with _connection() as connection:
        existing = connection.execute(
            """
            SELECT * FROM pending_actions
            WHERE item_id = ? AND action_type = ? AND status = 'pending' AND owner_id = ?
            """,
            (item_id, action_type, owner_id),
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

        insert_query = """
            INSERT INTO pending_actions (item_id, action_type, payload, status, created_at, owner_id)
            VALUES (?, ?, ?, 'pending', ?, ?)
        """
        cursor = connection.execute(
            f"{insert_query} RETURNING id" if USING_POSTGRES else insert_query,
            (item_id, action_type, json.dumps(payload), datetime.now().astimezone().isoformat(), owner_id),
        )
        action_id = cursor.fetchone()["id"] if USING_POSTGRES else cursor.lastrowid
        row = connection.execute(
            "SELECT * FROM pending_actions WHERE id = ?", (action_id,)
        ).fetchone()
    return _row_to_pending_action(row)


def get_pending_actions(owner_id: str = DEFAULT_OWNER_ID) -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT pending_actions.*, items.text AS item_text
            FROM pending_actions
            JOIN items ON items.id = pending_actions.item_id
            WHERE pending_actions.status = 'pending' AND pending_actions.owner_id = ? AND items.owner_id = ?
            ORDER BY pending_actions.created_at ASC
            """, (owner_id, owner_id)
        ).fetchall()
    return [_row_to_pending_action(row) for row in rows]


def approve_pending_action(action_id: int, owner_id: str = DEFAULT_OWNER_ID) -> dict[str, Any] | None:
    """Apply a pending action exactly once and record its approval."""
    with _connection() as connection:
        action = connection.execute(
            "SELECT * FROM pending_actions WHERE id = ? AND status = 'pending' AND owner_id = ?", (action_id, owner_id)
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
            "UPDATE items SET status = 'done' WHERE id = ? AND status = 'open' AND owner_id = ?", (action["item_id"], owner_id)
        )
        if completed.rowcount != 1:
            return None
        connection.execute(
            "UPDATE pending_actions SET status = 'approved' WHERE id = ?", (action_id,)
        )
        updated = connection.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,)).fetchone()
    return _row_to_pending_action(updated)


def reject_pending_action(action_id: int, owner_id: str = DEFAULT_OWNER_ID) -> dict[str, Any] | None:
    """Reject a pending action without applying its underlying change."""
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE pending_actions SET status = 'rejected' WHERE id = ? AND status = 'pending' AND owner_id = ?",
            (action_id, owner_id),
        )
        if cursor.rowcount != 1:
            return None
        updated = connection.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,)).fetchone()
    return _row_to_pending_action(updated)


def replace_study_plan(
    topics: list[dict[str, Any]],
    question_bank_archived_path: str | None = None,
    unit_notes_archived_path: str | None = None,
    owner_id: str = DEFAULT_OWNER_ID,
) -> list[dict[str, Any]]:
    """Store the latest study plan, replacing the previous local plan."""
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        connection.execute("DELETE FROM study_plans WHERE owner_id = ?", (owner_id,))
        connection.executemany(
            """
            INSERT INTO study_plans (
                topic, weight, subtopics, created_at,
                question_bank_archived_path, unit_notes_archived_path, owner_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    topic["topic"],
                    topic["weight"],
                    json.dumps(topic["subtopics"]),
                    created_at,
                    question_bank_archived_path,
                    unit_notes_archived_path,
                    owner_id,
                )
                for topic in topics
            ],
        )
    return get_study_plan(owner_id)


def get_study_plan(owner_id: str = DEFAULT_OWNER_ID) -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM study_plans WHERE owner_id = ? ORDER BY weight DESC, id ASC", (owner_id,)
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


def create_assignment_help(prompt: str, scaffold: dict[str, Any], owner_id: str = DEFAULT_OWNER_ID) -> dict[str, Any] | None:
    """Persist one assignment scaffold and return its stored record."""
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        insert_query = """
            INSERT INTO assignment_help (prompt, requirements, concepts, approach, test_cases, created_at, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor = connection.execute(
            f"{insert_query} RETURNING id" if USING_POSTGRES else insert_query,
            (
                prompt.strip(),
                json.dumps(scaffold["requirements"]),
                json.dumps(scaffold["concepts"]),
                json.dumps(scaffold["approach"]),
                json.dumps(scaffold["test_cases"]),
                created_at,
                owner_id,
            ),
        )
        assignment_id = cursor.fetchone()["id"] if USING_POSTGRES else cursor.lastrowid
        row = connection.execute(
            "SELECT * FROM assignment_help WHERE id = ?", (assignment_id,)
        ).fetchone()
    return _row_to_assignment_help(row) if row else None


def get_assignment_history(owner_id: str = DEFAULT_OWNER_ID) -> list[dict[str, Any]]:
    """Return saved assignment scaffolds with the newest first."""
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM assignment_help WHERE owner_id = ? ORDER BY created_at DESC, id DESC", (owner_id,)
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
