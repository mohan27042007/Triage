"""Isolated policy and execution checks for the opt-in Google pilot worker."""

import os
import unittest

import autonomous_google_worker as worker


PASSING_METRICS = {
    "invalid_outputs": [],
    "accuracy": 0.95,
    "obligation_recall": 1.0,
    "must_detect_recall": 1.0,
    "false_obligation_rate": 0.05,
}
JOB = {"id": 1, "source": "gmail", "owner_id": "student-a", "workspace_id": 101}


class AutonomousGoogleWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_environment = dict(os.environ)
        os.environ["AUTONOMOUS_GOOGLE_SYNC_ENABLED"] = "true"
        os.environ["AUTONOMOUS_GOOGLE_PILOT_WORKSPACE_IDS"] = "101"
        os.environ["AUTONOMOUS_EVALUATION_METRICS_JSON"] = __import__("json").dumps(PASSING_METRICS)
        self.original_runtime = worker.get_source_connection_runtime
        self.original_ingest = worker.ingest_source_changes
        self.original_record_sync = worker.record_source_sync
        self.original_record_outcome = worker.record_source_connection_outcome

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.original_environment)
        worker.get_source_connection_runtime = self.original_runtime
        worker.ingest_source_changes = self.original_ingest
        worker.record_source_sync = self.original_record_sync
        worker.record_source_connection_outcome = self.original_record_outcome

    def test_execution_requires_enabled_allowlisted_connection_and_records_success(self) -> None:
        events = []
        worker.get_source_connection_runtime = lambda source, owner_id: {
            "workspace_id": 101, "state": "enabled", "selected_channels": ["inbox"], "provider_cursor": None
        }
        worker.ingest_source_changes = lambda *args, **kwargs: {"processed": 2, "skipped": 1, "next_cursor": None}
        worker.record_source_sync = lambda *args, **kwargs: events.append(("sync", kwargs))
        worker.record_source_connection_outcome = lambda *args, **kwargs: events.append(("health", kwargs))

        outcome = worker.execute_sync_job(JOB)

        self.assertEqual(outcome, {"processed": 2, "skipped": 1, "source": "gmail"})
        self.assertEqual([event[0] for event in events], ["sync", "health"])

    def test_gate_blocks_missing_metrics_and_execution_failure_is_redacted(self) -> None:
        del os.environ["AUTONOMOUS_EVALUATION_METRICS_JSON"]
        with self.assertRaisesRegex(worker.PilotBlockedError, "evaluation_metrics_missing_or_invalid"):
            worker.execute_sync_job(JOB)

        os.environ["AUTONOMOUS_EVALUATION_METRICS_JSON"] = __import__("json").dumps(PASSING_METRICS)
        worker.get_source_connection_runtime = lambda source, owner_id: {
            "workspace_id": 101, "state": "enabled", "selected_channels": ["inbox"], "provider_cursor": None
        }
        worker.ingest_source_changes = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider detail"))
        recorded_errors = []
        worker.record_source_sync = lambda *args, **kwargs: recorded_errors.append(kwargs["error_message"])
        worker.record_source_connection_outcome = lambda *args, **kwargs: recorded_errors.append(kwargs["error_message"])

        with self.assertRaisesRegex(worker.PilotBlockedError, "google_sync_failed"):
            worker.execute_sync_job(JOB)
        self.assertEqual(recorded_errors, ["google_sync_failed", "google_sync_failed"])


if __name__ == "__main__":
    unittest.main()
