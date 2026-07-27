"""Isolated durability checks for leased workspace sync jobs."""

import gc
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

import database
import sync_jobs


class SyncJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.original_path = database.DATABASE_PATH
        self.original_postgres = database.USING_POSTGRES
        self.original_connection = database._connection
        self.connections: list[sqlite3.Connection] = []
        database.DATABASE_PATH = Path(self.temporary_directory.name) / "sync-jobs.db"
        database.USING_POSTGRES = False
        database._connection = self._temporary_connection
        database.initialize_database()
        database.enable_source_connection(
            "gmail", "google-connection:student-a", owner_id="student-a", workspace_id=101
        )

    def _temporary_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(database.DATABASE_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        self.connections.append(connection)
        return connection

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.original_path
        database.USING_POSTGRES = self.original_postgres
        database._connection = self.original_connection
        for connection in self.connections:
            connection.close()
        gc.collect()
        self.temporary_directory.cleanup()

    def _enqueue(self, key: str = "student-a:gmail:run-1", **kwargs):
        kwargs.setdefault("available_at", "2026-07-26T00:00:00+00:00")
        return sync_jobs.enqueue_sync_job(
            "gmail", workspace_id=101, owner_id="student-a", idempotency_key=key, **kwargs
        )

    def test_idempotency_and_two_workers_allow_only_one_active_lease(self) -> None:
        original = self._enqueue()
        duplicate = self._enqueue()

        first_claim = sync_jobs.claim_next_sync_job("worker-one", now="2026-07-27T00:00:00+00:00")
        second_claim = sync_jobs.claim_next_sync_job("worker-two", now="2026-07-27T00:00:01+00:00")

        self.assertEqual(original["id"], duplicate["id"])
        self.assertEqual(first_claim["state"], "running")
        self.assertEqual(first_claim["attempt_count"], 1)
        self.assertIsNone(second_claim)

    def test_expired_lease_is_reclaimed_after_worker_restart(self) -> None:
        job = self._enqueue()
        first_claim = sync_jobs.claim_next_sync_job(
            "worker-before-restart", lease_seconds=30, now="2026-07-27T00:00:00+00:00"
        )
        recovered = sync_jobs.claim_next_sync_job(
            "worker-after-restart", lease_seconds=30, now="2026-07-27T00:00:31+00:00"
        )

        self.assertEqual(recovered["id"], job["id"])
        self.assertEqual(recovered["attempt_count"], 2)
        self.assertNotEqual(recovered["lease_token"], first_claim["lease_token"])

    def test_failures_retry_then_become_terminal_and_pause_cancels_work(self) -> None:
        job = self._enqueue(max_attempts=2)
        first_claim = sync_jobs.claim_next_sync_job("worker-one")
        retry = sync_jobs.fail_sync_job(
            first_claim["id"], first_claim["lease_token"], "provider_unavailable", retry_after_seconds=0
        )
        second_claim = sync_jobs.claim_next_sync_job("worker-two")
        terminal = sync_jobs.fail_sync_job(
            second_claim["id"], second_claim["lease_token"], "provider_unavailable", retry_after_seconds=0
        )

        self.assertEqual(retry["state"], "queued")
        self.assertEqual(terminal["state"], "failed")
        pending = self._enqueue("student-a:gmail:run-2")
        database.set_source_connection_state("gmail", "paused", owner_id="student-a")
        self.assertEqual(sync_jobs.get_sync_job(pending["id"])["state"], "cancelled")

    def test_run_once_records_a_structured_outcome(self) -> None:
        self._enqueue()
        result = sync_jobs.run_once(lambda job: {"imported_count": 0, "source": job["source"]}, worker_id="worker-one")

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["job"]["state"], "succeeded")
        self.assertEqual(result["job"]["outcome"], {"imported_count": 0, "source": "gmail"})


if __name__ == "__main__":
    unittest.main()
