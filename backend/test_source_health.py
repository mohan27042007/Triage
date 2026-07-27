"""Isolated checks for per-owner, persisted source sync health.

Run with: python test_source_health.py
This test uses a temporary database and never opens backend/triage.db.
"""

import gc
from pathlib import Path
from tempfile import TemporaryDirectory

import database


def main() -> None:
    original_path = database.DATABASE_PATH
    original_postgres = database.USING_POSTGRES
    with TemporaryDirectory() as temporary_directory:
        database.DATABASE_PATH = Path(temporary_directory) / "source-health.db"
        database.USING_POSTGRES = False
        try:
            database.initialize_database()
            assert database.get_source_sync_status("student-a") == {}

            database.record_source_sync("gmail", succeeded=True, imported_count=3, owner_id="student-a", workspace_id=101)
            first = database.get_source_sync_status("student-a")["gmail"]
            assert first["last_success_at"] == first["last_attempt_at"]
            assert first["last_imported_count"] == 3
            assert first["last_error"] is None

            database.record_source_sync("gmail", succeeded=False, error_message="x" * 200, owner_id="student-a", workspace_id=101)
            failed = database.get_source_sync_status("student-a")["gmail"]
            assert failed["last_error"] == "x" * 160
            assert failed["last_success_at"] == first["last_success_at"]
            assert failed["last_imported_count"] == 3

            database.record_source_sync("gmail", succeeded=True, imported_count=1, owner_id="student-a")
            recovered = database.get_source_sync_status("student-a")["gmail"]
            assert recovered["last_error"] is None
            assert recovered["last_imported_count"] == 1

            database.record_source_sync("classroom", succeeded=True, imported_count=0, owner_id="student-b")
            assert set(database.get_source_sync_status("student-a")) == {"gmail"}
            assert set(database.get_source_sync_status("student-b")) == {"classroom"}
        finally:
            database.DATABASE_PATH = original_path
            database.USING_POSTGRES = original_postgres
            gc.collect()

    print("Source health checks passed.")


if __name__ == "__main__":
    main()
