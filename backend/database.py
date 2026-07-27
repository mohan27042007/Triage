"""User-scoped persistence for local SQLite and hosted PostgreSQL deployments."""

import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from postgres_migrations import CORE_POSTGRES_MIGRATIONS, apply_postgres_migrations

DATABASE_PATH = Path(__file__).with_name("triage.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USING_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
DEFAULT_OWNER_ID = "local-demo"
VALID_ITEM_SOURCES = {"manual", "gmail", "classroom", "whatsapp-demo"}
VALID_CONNECTED_SOURCES = {"gmail", "classroom"}
VALID_SOURCE_CONNECTION_STATES = {"enabled", "paused"}
SCHEMA_MIGRATION_IDS = (
    "2026-07-26-data-safeguards-v1",
    "2026-07-26-source-health-v1",
    "2026-07-27-workspace-foundation-v1",
)


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
                owner_id TEXT NOT NULL DEFAULT 'local-demo',
                workspace_id INTEGER
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
                owner_id TEXT NOT NULL DEFAULT 'local-demo',
                workspace_id INTEGER
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
                workspace_id INTEGER,
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
                owner_id TEXT NOT NULL DEFAULT 'local-demo',
                workspace_id INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_sync_status (
                owner_id TEXT NOT NULL,
                source TEXT NOT NULL,
                last_attempt_at TEXT NOT NULL,
                last_success_at TEXT,
                last_error TEXT,
                last_imported_count INTEGER,
                workspace_id INTEGER,
                PRIMARY KEY (owner_id, source)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_connections (
                owner_id TEXT NOT NULL,
                workspace_id INTEGER,
                source TEXT NOT NULL,
                credential_ref TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'enabled',
                selected_channels TEXT NOT NULL DEFAULT '[]',
                sync_interval_minutes INTEGER NOT NULL DEFAULT 30,
                provider_cursor TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (owner_id, source)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                owner_id TEXT NOT NULL,
                source TEXT NOT NULL CHECK (source IN ('gmail', 'classroom')),
                idempotency_key TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 5),
                available_at TEXT NOT NULL,
                lease_token TEXT,
                lease_expires_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                outcome TEXT,
                last_error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (workspace_id, source, idempotency_key)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sync_jobs_claim "
            "ON sync_jobs(state, available_at, lease_expires_at)"
        )
        _add_column_if_missing(connection, "items", "archived_path", "TEXT")
        _add_column_if_missing(connection, "items", "attachments", "TEXT NOT NULL DEFAULT '[]'")
        _add_column_if_missing(connection, "items", "source_id", "TEXT")
        _add_column_if_missing(connection, "items", "is_poll_or_form", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(connection, "items", "owner_id", "TEXT NOT NULL DEFAULT 'local-demo'")
        _add_column_if_missing(connection, "items", "workspace_id", "INTEGER")
        _add_column_if_missing(connection, "study_plans", "question_bank_archived_path", "TEXT")
        _add_column_if_missing(connection, "study_plans", "unit_notes_archived_path", "TEXT")
        _add_column_if_missing(connection, "study_plans", "owner_id", "TEXT NOT NULL DEFAULT 'local-demo'")
        _add_column_if_missing(connection, "study_plans", "workspace_id", "INTEGER")
        _add_column_if_missing(connection, "pending_actions", "owner_id", "TEXT NOT NULL DEFAULT 'local-demo'")
        _add_column_if_missing(connection, "pending_actions", "workspace_id", "INTEGER")
        _add_column_if_missing(connection, "assignment_help", "owner_id", "TEXT NOT NULL DEFAULT 'local-demo'")
        _add_column_if_missing(connection, "assignment_help", "workspace_id", "INTEGER")
        _add_column_if_missing(connection, "source_sync_status", "workspace_id", "INTEGER")
        connection.execute("DROP INDEX IF EXISTS idx_items_source_id")
        connection.execute("DROP INDEX IF EXISTS idx_items_owner_source_id")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_workspace_source_id "
            "ON items(workspace_id, source, source_id) "
            "WHERE workspace_id IS NOT NULL AND source_id IS NOT NULL"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_local_owner_source_id "
            "ON items(owner_id, source, source_id) "
            "WHERE workspace_id IS NULL AND source_id IS NOT NULL"
        )
        _record_schema_migration(connection)


def _initialize_postgres_database() -> None:
    """Apply ordered core-schema migrations without modifying local SQLite data."""
    with _connection() as connection:
        apply_postgres_migrations(connection, CORE_POSTGRES_MIGRATIONS)


def _record_schema_migration(connection) -> None:
    """Maintain an additive schema ledger without rewriting user data."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.executemany(
        "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
        [(migration_id, datetime.now().astimezone().isoformat()) for migration_id in SCHEMA_MIGRATION_IDS],
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
    owner_id: str = DEFAULT_OWNER_ID,
    workspace_id: int | None = None,
) -> dict[str, Any] | None:
    """Persist one classified item and return the stored record."""
    if source not in VALID_ITEM_SOURCES:
        raise ValueError(f"Unsupported item source: {source}")
    if source_id is not None:
        existing = get_item_by_source_id(
            source, source_id, owner_id=owner_id, workspace_id=workspace_id
        )
        if existing is not None:
            return existing
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        insert_query = """
            INSERT INTO items (
                text, category, reason, deadline, mandatory, source,
                created_at, status, archived_path, attachments, source_id, is_poll_or_form, owner_id, workspace_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)
        """
        insert_with_conflict_handling = f"{insert_query} ON CONFLICT DO NOTHING"
        cursor = connection.execute(
            f"{insert_with_conflict_handling} RETURNING id" if USING_POSTGRES else insert_with_conflict_handling,
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
                workspace_id,
            ),
        )
        if USING_POSTGRES:
            row = cursor.fetchone()
            item_id = row["id"] if row else None
        else:
            item_id = cursor.lastrowid if cursor.rowcount == 1 else None
    if item_id is None and source_id is not None:
        return get_item_by_source_id(source, source_id, owner_id=owner_id, workspace_id=workspace_id)
    return get_item(item_id, owner_id) if item_id else None


def get_item(item_id: int, owner_id: str = DEFAULT_OWNER_ID) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute("SELECT * FROM items WHERE id = ? AND owner_id = ?", (item_id, owner_id)).fetchone()
    return _row_to_item(row) if row else None


def get_item_by_source_id(
    source: str,
    source_id: str,
    *,
    owner_id: str = DEFAULT_OWNER_ID,
    workspace_id: int | None = None,
) -> dict[str, Any] | None:
    """Return one item using the workspace/provider/source-item identity key."""
    if source not in VALID_ITEM_SOURCES:
        raise ValueError(f"Unsupported item source: {source}")
    with _connection() as connection:
        if workspace_id is None:
            row = connection.execute(
                "SELECT * FROM items WHERE source = ? AND source_id = ? AND owner_id = ? AND workspace_id IS NULL",
                (source, source_id, owner_id),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM items WHERE source = ? AND source_id = ? AND workspace_id = ?",
                (source, source_id, workspace_id),
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


SOURCE_SYNC_SOURCES = {"gmail", "classroom"}


def record_source_sync(
    source: str,
    *,
    succeeded: bool,
    imported_count: int | None = None,
    error_message: str | None = None,
    owner_id: str = DEFAULT_OWNER_ID,
    workspace_id: int | None = None,
) -> None:
    """Store the outcome of one user-requested, read-only source sync."""
    if source not in SOURCE_SYNC_SOURCES:
        raise ValueError("Unsupported source sync status.")
    attempted_at = datetime.now().astimezone().isoformat()
    successful_at = attempted_at if succeeded else None
    safe_error = (error_message or "").strip()[:160] or None
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO source_sync_status (
                owner_id, source, last_attempt_at, last_success_at, last_error, last_imported_count, workspace_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (owner_id, source) DO UPDATE SET
                last_attempt_at = excluded.last_attempt_at,
                last_success_at = CASE
                    WHEN excluded.last_success_at IS NOT NULL THEN excluded.last_success_at
                    ELSE source_sync_status.last_success_at
                END,
                last_error = excluded.last_error,
                last_imported_count = CASE
                    WHEN excluded.last_imported_count IS NOT NULL THEN excluded.last_imported_count
                    ELSE source_sync_status.last_imported_count
                END,
                workspace_id = COALESCE(excluded.workspace_id, source_sync_status.workspace_id)
            """,
            (owner_id, source, attempted_at, successful_at, safe_error, imported_count, workspace_id),
        )


def get_source_sync_status(owner_id: str = DEFAULT_OWNER_ID) -> dict[str, dict[str, Any]]:
    """Return the last persisted sync outcome for each supported live source."""
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT source, last_attempt_at, last_success_at, last_error, last_imported_count
            FROM source_sync_status WHERE owner_id = ?
            """,
            (owner_id,),
        ).fetchall()
    return {
        row["source"]: {
            "last_attempt_at": row["last_attempt_at"],
            "last_success_at": row["last_success_at"],
            "last_error": row["last_error"],
            "last_imported_count": row["last_imported_count"],
        }
        for row in rows
    }


def enable_source_connection(
    source: str,
    credential_ref: str,
    *,
    owner_id: str = DEFAULT_OWNER_ID,
    workspace_id: int | None = None,
    selected_channels: list[str] | None = None,
    sync_interval_minutes: int = 30,
) -> dict[str, Any]:
    """Persist an enabled source connection without storing provider credentials."""
    if source not in VALID_CONNECTED_SOURCES:
        raise ValueError("Unsupported source connection.")
    if not isinstance(credential_ref, str) or not credential_ref.strip():
        raise ValueError("Source connections require a credential reference.")
    if not 15 <= sync_interval_minutes <= 1_440:
        raise ValueError("Sync interval must be between 15 and 1440 minutes.")
    channels = selected_channels or []
    if not isinstance(channels, list) or not all(isinstance(channel, str) and channel.strip() for channel in channels):
        raise ValueError("Selected channels must be a list of non-empty names.")
    now = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO source_connections (
                owner_id, workspace_id, source, credential_ref, state, selected_channels,
                sync_interval_minutes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'enabled', ?, ?, ?, ?)
            ON CONFLICT (owner_id, source) DO UPDATE SET
                workspace_id = COALESCE(excluded.workspace_id, source_connections.workspace_id),
                credential_ref = excluded.credential_ref,
                state = 'enabled',
                selected_channels = excluded.selected_channels,
                sync_interval_minutes = excluded.sync_interval_minutes,
                updated_at = excluded.updated_at
            """,
            (
                owner_id,
                workspace_id,
                source,
                credential_ref.strip(),
                json.dumps(channels),
                sync_interval_minutes,
                now,
                now,
            ),
        )
    connection_record = get_source_connection(source, owner_id=owner_id)
    if connection_record is None:
        raise RuntimeError("Could not save source connection.")
    return connection_record


def get_source_connection(source: str, *, owner_id: str = DEFAULT_OWNER_ID) -> dict[str, Any] | None:
    """Return one source connection without exposing its credential reference."""
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM source_connections WHERE owner_id = ? AND source = ?", (owner_id, source)
        ).fetchone()
    return _row_to_source_connection(row) if row else None


def get_source_connections(owner_id: str = DEFAULT_OWNER_ID) -> list[dict[str, Any]]:
    """Return source-connection health for one owner."""
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM source_connections WHERE owner_id = ? ORDER BY source ASC", (owner_id,)
        ).fetchall()
    return [_row_to_source_connection(row) for row in rows]


def set_source_connection_state(
    source: str, state: str, *, owner_id: str = DEFAULT_OWNER_ID
) -> dict[str, Any] | None:
    """Pause or resume a saved source connection without deleting its configuration."""
    if source not in VALID_CONNECTED_SOURCES or state not in VALID_SOURCE_CONNECTION_STATES:
        raise ValueError("Unsupported source connection state.")
    now = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE source_connections SET state = ?, updated_at = ? WHERE owner_id = ? AND source = ?",
            (state, now, owner_id, source),
        )
        if cursor.rowcount != 1:
            return None
        if state == "paused":
            connection.execute(
                """
                UPDATE sync_jobs
                SET state = 'cancelled', lease_token = NULL, lease_expires_at = NULL,
                    completed_at = ?, updated_at = ?
                WHERE source = ? AND owner_id = ? AND state IN ('queued', 'running')
                """,
                (now, now, source, owner_id),
            )
    return get_source_connection(source, owner_id=owner_id)


def is_source_connection_paused(source: str, *, owner_id: str = DEFAULT_OWNER_ID) -> bool:
    connection = get_source_connection(source, owner_id=owner_id)
    return connection is not None and connection["state"] == "paused"


def record_source_connection_outcome(
    source: str,
    *,
    succeeded: bool,
    error_message: str | None = None,
    owner_id: str = DEFAULT_OWNER_ID,
) -> None:
    """Update connection health after a manual or future worker-driven sync."""
    if source not in VALID_CONNECTED_SOURCES:
        raise ValueError("Unsupported source connection.")
    attempted_at = datetime.now().astimezone().isoformat()
    safe_error = (error_message or "").strip()[:160] or None
    with _connection() as connection:
        connection.execute(
            """
            UPDATE source_connections SET
                last_attempt_at = ?,
                last_success_at = CASE WHEN ? THEN ? ELSE last_success_at END,
                last_error = ?,
                consecutive_failures = CASE WHEN ? THEN 0 ELSE consecutive_failures + 1 END,
                updated_at = ?
            WHERE owner_id = ? AND source = ?
            """,
            (attempted_at, succeeded, attempted_at, safe_error, succeeded, attempted_at, owner_id, source),
        )


def _row_to_source_connection(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "source": row["source"],
        "workspace_id": row["workspace_id"],
        "state": row["state"],
        "selected_channels": json.loads(row["selected_channels"]),
        "sync_interval_minutes": row["sync_interval_minutes"],
        "provider_cursor_configured": bool(row["provider_cursor"]),
        "consecutive_failures": row["consecutive_failures"],
        "last_attempt_at": row["last_attempt_at"],
        "last_success_at": row["last_success_at"],
        "last_error": row["last_error"],
        "has_credential": bool(row["credential_ref"]),
    }


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
    item_id: int,
    action_type: str,
    payload: dict[str, Any],
    owner_id: str = DEFAULT_OWNER_ID,
    workspace_id: int | None = None,
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
            INSERT INTO pending_actions (item_id, action_type, payload, status, created_at, owner_id, workspace_id)
            VALUES (?, ?, ?, 'pending', ?, ?, ?)
        """
        cursor = connection.execute(
            f"{insert_query} RETURNING id" if USING_POSTGRES else insert_query,
            (item_id, action_type, json.dumps(payload), datetime.now().astimezone().isoformat(), owner_id, workspace_id),
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
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    """Store the latest study plan, replacing the previous local plan."""
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        connection.execute("DELETE FROM study_plans WHERE owner_id = ?", (owner_id,))
        connection.executemany(
            """
            INSERT INTO study_plans (
                topic, weight, subtopics, created_at,
                question_bank_archived_path, unit_notes_archived_path, owner_id, workspace_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                    workspace_id,
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


def create_assignment_help(
    prompt: str,
    scaffold: dict[str, Any],
    owner_id: str = DEFAULT_OWNER_ID,
    workspace_id: int | None = None,
) -> dict[str, Any] | None:
    """Persist one assignment scaffold and return its stored record."""
    created_at = datetime.now().astimezone().isoformat()
    with _connection() as connection:
        insert_query = """
            INSERT INTO assignment_help (prompt, requirements, concepts, approach, test_cases, created_at, owner_id, workspace_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                workspace_id,
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


def export_owner_data(owner_id: str = DEFAULT_OWNER_ID) -> dict[str, Any]:
    """Create a portable metadata export for one owner; archived bytes stay private."""
    with _connection() as connection:
        item_rows = connection.execute(
            "SELECT * FROM items WHERE owner_id = ? ORDER BY created_at DESC, id DESC", (owner_id,)
        ).fetchall()
        action_rows = connection.execute(
            "SELECT * FROM pending_actions WHERE owner_id = ? ORDER BY created_at DESC, id DESC", (owner_id,)
        ).fetchall()
        migration_rows = connection.execute(
            "SELECT id, applied_at FROM schema_migrations ORDER BY applied_at ASC"
        ).fetchall()

    return {
        "format": "triage-data-export/v1",
        "exported_at": datetime.now().astimezone().isoformat(),
        "schema_migrations": [dict(row) for row in migration_rows],
        "items": [_row_to_item(row) for row in item_rows],
        "pending_actions": [_row_to_pending_action(row) for row in action_rows],
        "study_plan": get_study_plan(owner_id),
        "assignment_scaffolds": get_assignment_history(owner_id),
        "archive_manifest": get_archived_attachments(owner_id),
        "note": "Archived file bytes and browser-only form details are intentionally excluded.",
    }


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
