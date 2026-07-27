"""Ordered, transactional PostgreSQL schema migrations for hosted Triage."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from workspace_foundation import initialize_workspace_foundation


MigrationApply = Callable[[object], None]
MIGRATION_LOCK_ID = 7_263_119


@dataclass(frozen=True)
class PostgresMigration:
    identifier: str
    apply: MigrationApply


def apply_postgres_migrations(connection, migrations: Sequence[PostgresMigration]) -> list[str]:
    """Apply ordered migrations once under a transaction-scoped PostgreSQL advisory lock."""
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
    connection.execute("""
        CREATE TABLE IF NOT EXISTS postgres_schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    applied_ids = {row["id"] for row in connection.execute("SELECT id FROM postgres_schema_migrations").fetchall()}
    newly_applied: list[str] = []
    for migration in migrations:
        if migration.identifier in applied_ids:
            continue
        migration.apply(connection)
        connection.execute(
            "INSERT INTO postgres_schema_migrations (id) VALUES (%s)",
            (migration.identifier,),
        )
        newly_applied.append(migration.identifier)
    return newly_applied


def _create_core_schema(connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id BIGSERIAL PRIMARY KEY, text TEXT NOT NULL, category TEXT NOT NULL,
            reason TEXT NOT NULL, deadline TEXT, mandatory BOOLEAN, source TEXT NOT NULL,
            created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', archived_path TEXT,
            attachments TEXT NOT NULL DEFAULT '[]', source_id TEXT, is_poll_or_form BOOLEAN NOT NULL DEFAULT FALSE,
            owner_id TEXT NOT NULL, workspace_id BIGINT
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS study_plans (
            id BIGSERIAL PRIMARY KEY, topic TEXT NOT NULL, weight INTEGER NOT NULL,
            subtopics TEXT NOT NULL, created_at TEXT NOT NULL, question_bank_archived_path TEXT,
            unit_notes_archived_path TEXT, owner_id TEXT NOT NULL, workspace_id BIGINT
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS pending_actions (
            id BIGSERIAL PRIMARY KEY, item_id BIGINT NOT NULL REFERENCES items(id),
            action_type TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL, owner_id TEXT NOT NULL, workspace_id BIGINT
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS assignment_help (
            id BIGSERIAL PRIMARY KEY, prompt TEXT NOT NULL, requirements TEXT NOT NULL,
            concepts TEXT NOT NULL, approach TEXT NOT NULL, test_cases TEXT NOT NULL,
            created_at TEXT NOT NULL, owner_id TEXT NOT NULL, workspace_id BIGINT
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS source_sync_status (
            owner_id TEXT NOT NULL,
            source TEXT NOT NULL,
            last_attempt_at TEXT NOT NULL,
            last_success_at TEXT,
            last_error TEXT,
            last_imported_count INTEGER,
            workspace_id BIGINT,
            PRIMARY KEY (owner_id, source)
        )
    """)
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_owner_source_id "
        "ON items(owner_id, source_id) WHERE source_id IS NOT NULL"
    )


def _ensure_core_workspace_columns(connection) -> None:
    for table in ("items", "study_plans", "pending_actions", "assignment_help", "source_sync_status"):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS workspace_id BIGINT")


def _create_hosted_auth_schema(connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY, google_subject TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL, display_name TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS google_connections (
            user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            encrypted_credentials BYTEA NOT NULL, scopes TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS api_sessions (
            token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS oauth_states (
            state_hash TEXT PRIMARY KEY, code_verifier TEXT NOT NULL, return_to TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint_hash TEXT NOT NULL UNIQUE, encrypted_subscription BYTEA NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS reminder_deliveries (
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reminder_window TEXT NOT NULL, reminder_date DATE NOT NULL,
            delivered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, reminder_window, reminder_date)
        )
    """)


CORE_POSTGRES_MIGRATIONS = (
    PostgresMigration("2026-07-26-core-schema-v1", _create_core_schema),
    PostgresMigration("2026-07-27-core-workspace-columns-v1", _ensure_core_workspace_columns),
)

HOSTED_POSTGRES_MIGRATIONS = (
    PostgresMigration("2026-07-26-hosted-auth-schema-v1", _create_hosted_auth_schema),
    PostgresMigration("2026-07-27-personal-workspaces-v1", initialize_workspace_foundation),
)
