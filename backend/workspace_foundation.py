"""Additive PostgreSQL helpers for Triage's personal-workspace foundation."""


WORKSPACE_BACKFILL_TABLES = (
    "items",
    "study_plans",
    "pending_actions",
    "assignment_help",
    "source_sync_status",
)


def initialize_workspace_foundation(connection) -> None:
    """Create personal workspaces and backfill hosted records without deleting data."""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('personal', 'organization')),
            personal_owner_id BIGINT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS workspace_memberships (
            workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('individual', 'member', 'admin')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (workspace_id, user_id)
        )
    """)
    for table in WORKSPACE_BACKFILL_TABLES:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS workspace_id BIGINT")
    connection.execute("""
        INSERT INTO workspaces (name, kind, personal_owner_id)
        SELECT COALESCE(NULLIF(users.display_name, '') || '''s workspace', 'Personal workspace'),
               'personal', users.id
        FROM users
        ON CONFLICT (personal_owner_id) DO NOTHING
    """)
    connection.execute("""
        INSERT INTO workspace_memberships (workspace_id, user_id, role)
        SELECT workspaces.id, users.id, 'individual'
        FROM users
        JOIN workspaces ON workspaces.personal_owner_id = users.id
        ON CONFLICT (workspace_id, user_id) DO NOTHING
    """)
    for table in WORKSPACE_BACKFILL_TABLES:
        connection.execute(f"""
            UPDATE {table}
            SET workspace_id = workspace_memberships.workspace_id
            FROM workspace_memberships
            WHERE {table}.workspace_id IS NULL
              AND {table}.owner_id = workspace_memberships.user_id::TEXT
              AND workspace_memberships.role = 'individual'
        """)


def ensure_personal_workspace(connection, user_id: int, display_name: str | None) -> int:
    """Create a stable personal workspace for one hosted user if it is missing."""
    name = f"{display_name.strip()}'s workspace" if display_name and display_name.strip() else "Personal workspace"
    workspace = connection.execute(
        """
        INSERT INTO workspaces (name, kind, personal_owner_id)
        VALUES (%s, 'personal', %s)
        ON CONFLICT (personal_owner_id) DO UPDATE SET personal_owner_id = EXCLUDED.personal_owner_id
        RETURNING id
        """,
        (name, user_id),
    ).fetchone()
    connection.execute(
        """
        INSERT INTO workspace_memberships (workspace_id, user_id, role)
        VALUES (%s, %s, 'individual')
        ON CONFLICT (workspace_id, user_id) DO NOTHING
        """,
        (workspace["id"], user_id),
    )
    return int(workspace["id"])
