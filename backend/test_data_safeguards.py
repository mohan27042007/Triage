"""Isolated database checks for schema tracking and owner-scoped exports."""

import gc
from pathlib import Path
from tempfile import TemporaryDirectory

import database


def main() -> None:
    original_path = database.DATABASE_PATH
    original_postgres = database.USING_POSTGRES
    with TemporaryDirectory() as temporary_directory:
        database.DATABASE_PATH = Path(temporary_directory) / "test-triage.db"
        database.USING_POSTGRES = False
        try:
            database.initialize_database()
            item = database.create_item(
                "Submit the library form by 2026-08-01.",
                {"category": "Obligation", "reason": "Explicit form deadline.", "deadline": "2026-08-01", "mandatory": True},
                owner_id="student-a",
                workspace_id=101,
            )
            assert item is not None
            assert item["workspace_id"] == 101
            action = database.create_pending_action(
                item["id"], "mark_done", {"item_id": item["id"]}, owner_id="student-a", workspace_id=101
            )
            assert action["workspace_id"] == 101
            database.create_item(
                "Other student's private notice.",
                {"category": "Noise", "reason": "Not relevant.", "deadline": None, "mandatory": False},
                owner_id="student-b",
            )

            exported = database.export_owner_data("student-a")
            assert exported["format"] == "triage-data-export/v1"
            assert len(exported["items"]) == 1
            assert exported["items"][0]["text"].startswith("Submit")
            assert exported["items"][0]["workspace_id"] == 101
            assert len(exported["pending_actions"]) == 1
            assert exported["pending_actions"][0]["workspace_id"] == 101
            assert {entry["id"] for entry in exported["schema_migrations"]} == set(database.SCHEMA_MIGRATION_IDS)
            assert "Archived file bytes" in exported["note"]
        finally:
            database.DATABASE_PATH = original_path
            database.USING_POSTGRES = original_postgres
            gc.collect()

    print("Data safeguard checks passed.")


if __name__ == "__main__":
    main()
