"""Focused unit checks for the hosted personal-workspace foundation."""

import unittest

from workspace_foundation import ensure_personal_workspace, initialize_workspace_foundation


class _Result:
    def __init__(self, row=None) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _RecordingConnection:
    def __init__(self, workspace_id: int = 41) -> None:
        self.workspace_id = workspace_id
        self.queries: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, parameters: object = ()) -> _Result:
        self.queries.append((query, parameters))
        if "RETURNING id" in query or "SELECT workspace_id" in query:
            return _Result({"id": self.workspace_id, "workspace_id": self.workspace_id})
        return _Result()


class WorkspaceFoundationTests(unittest.TestCase):
    def test_workspace_schema_is_additive_and_backfills_existing_records(self) -> None:
        connection = _RecordingConnection()
        initialize_workspace_foundation(connection)
        queries = "\n".join(query for query, _ in connection.queries)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspaces", queries)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_memberships", queries)
        self.assertIn("ALTER TABLE items ADD COLUMN IF NOT EXISTS workspace_id BIGINT", queries)
        self.assertIn("UPDATE source_sync_status", queries)
        self.assertNotIn("DROP TABLE", queries)
        self.assertNotIn("DELETE FROM", queries)

    def test_personal_workspace_is_stable_and_membership_is_created(self) -> None:
        connection = _RecordingConnection(workspace_id=73)
        workspace_id = ensure_personal_workspace(connection, 7, "Asha")
        self.assertEqual(workspace_id, 73)
        queries = "\n".join(query for query, _ in connection.queries)
        self.assertIn("ON CONFLICT (personal_owner_id)", queries)
        self.assertIn("INSERT INTO workspace_memberships", queries)

if __name__ == "__main__":
    unittest.main()
