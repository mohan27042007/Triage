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
            review_required BOOLEAN NOT NULL DEFAULT FALSE, review_reasons TEXT NOT NULL DEFAULT '[]',
            draft_eligible BOOLEAN NOT NULL DEFAULT FALSE,
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
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_workspace_source_id "
        "ON items(workspace_id, source, source_id) "
        "WHERE workspace_id IS NOT NULL AND source_id IS NOT NULL"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_local_owner_source_id "
        "ON items(owner_id, source, source_id) "
        "WHERE workspace_id IS NULL AND source_id IS NOT NULL"
    )


def _ensure_core_workspace_columns(connection) -> None:
    for table in ("items", "study_plans", "pending_actions", "assignment_help", "source_sync_status"):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS workspace_id BIGINT")


def _add_policy_routing_columns(connection) -> None:
    """Add deterministic review fields without changing existing item data."""
    connection.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS review_required BOOLEAN NOT NULL DEFAULT FALSE")
    connection.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS review_reasons TEXT NOT NULL DEFAULT '[]'")
    connection.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS draft_eligible BOOLEAN NOT NULL DEFAULT FALSE")


def _create_hosted_auth_schema(connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY, google_subject TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL, display_name TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def _create_source_connections(connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS source_connections (
            owner_id TEXT NOT NULL,
            workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            source TEXT NOT NULL CHECK (source IN ('gmail', 'classroom')),
            credential_ref TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'enabled' CHECK (state IN ('enabled', 'paused')),
            selected_channels TEXT NOT NULL DEFAULT '[]',
            sync_interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (sync_interval_minutes BETWEEN 15 AND 1440),
            provider_cursor TEXT,
            consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
            last_attempt_at TEXT,
            last_success_at TEXT,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (owner_id, source),
            UNIQUE (workspace_id, source)
        )
    """)

    connection.execute("""
        INSERT INTO source_connections (
            owner_id, workspace_id, source, credential_ref, state, last_attempt_at,
            last_success_at, last_error, created_at, updated_at
        )
        SELECT source_sync_status.owner_id, source_sync_status.workspace_id,
               source_sync_status.source, 'google-connection:' || source_sync_status.owner_id,
               'enabled', source_sync_status.last_attempt_at, source_sync_status.last_success_at,
               source_sync_status.last_error, NOW(), NOW()
        FROM source_sync_status
        WHERE source_sync_status.workspace_id IS NOT NULL
          AND source_sync_status.source IN ('gmail', 'classroom')
        ON CONFLICT (owner_id, source) DO NOTHING
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


def _correct_item_dedupe(connection) -> None:
    """Replace owner-only source IDs with provider-aware workspace identities."""
    collision = connection.execute("""
        SELECT workspace_id, source, source_id
        FROM items
        WHERE workspace_id IS NOT NULL AND source_id IS NOT NULL
        GROUP BY workspace_id, source, source_id
        HAVING COUNT(*) > 1
        LIMIT 1
    """).fetchone()
    if collision is not None:
        raise RuntimeError(
            "Cannot apply workspace-source dedupe until duplicate workspace/provider/source IDs are resolved."
        )
    connection.execute("DROP INDEX IF EXISTS idx_items_owner_source_id")
    connection.execute("DROP INDEX IF EXISTS idx_items_source_id")
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


def _create_sync_jobs(connection) -> None:
    """Create the durable, leased job ledger without scheduling source work."""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS sync_jobs (
            id BIGSERIAL PRIMARY KEY,
            workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            owner_id TEXT NOT NULL,
            source TEXT NOT NULL CHECK (source IN ('gmail', 'classroom')),
            idempotency_key TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 5),
            available_at TIMESTAMPTZ NOT NULL,
            lease_token TEXT,
            lease_expires_at TIMESTAMPTZ,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            outcome JSONB,
            last_error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (workspace_id, source, idempotency_key)
        )
    """)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_sync_jobs_claim "
        "ON sync_jobs(state, available_at, lease_expires_at)"
    )


def _create_operational_controls(connection) -> None:
    """Create privacy-minimized operational records after workspace and job tables exist."""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id BIGSERIAL PRIMARY KEY,
            workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            owner_id TEXT NOT NULL,
            actor_type TEXT NOT NULL CHECK (actor_type IN ('system', 'user')),
            event_type TEXT NOT NULL,
            item_id BIGINT REFERENCES items(id) ON DELETE SET NULL,
            sync_job_id BIGINT REFERENCES sync_jobs(id) ON DELETE SET NULL,
            outcome TEXT NOT NULL,
            error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_workspace_created "
        "ON audit_events(workspace_id, created_at DESC)"
    )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS notification_deliveries (
            id BIGSERIAL PRIMARY KEY,
            workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            owner_id TEXT NOT NULL,
            notification_type TEXT NOT NULL,
            item_id BIGINT REFERENCES items(id) ON DELETE SET NULL,
            sync_job_id BIGINT REFERENCES sync_jobs(id) ON DELETE SET NULL,
            status TEXT NOT NULL,
            error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_deliveries_workspace_created "
        "ON notification_deliveries(workspace_id, created_at DESC)"
    )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS workspace_kill_switches (
            workspace_id BIGINT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by TEXT
        )
    """)


CORE_POSTGRES_MIGRATIONS = (
    PostgresMigration("2026-07-26-core-schema-v1", _create_core_schema),
    PostgresMigration("2026-07-27-core-workspace-columns-v1", _ensure_core_workspace_columns),
    PostgresMigration("2026-07-27-policy-routing-v1", _add_policy_routing_columns),
)

HOSTED_POSTGRES_MIGRATIONS = (
    PostgresMigration("2026-07-26-hosted-auth-schema-v1", _create_hosted_auth_schema),
    PostgresMigration("2026-07-27-personal-workspaces-v1", initialize_workspace_foundation),
    PostgresMigration("2026-07-27-source-connections-v1", _create_source_connections),
    PostgresMigration("2026-07-27-workspace-source-dedupe-v1", _correct_item_dedupe),
    PostgresMigration("2026-07-27-workspace-sync-jobs-v1", _create_sync_jobs),
    PostgresMigration("2026-07-27-workspace-sync-z-operational-controls-v1", _create_operational_controls),
)
