"""Short-lived scheduler command that only enqueues durable source jobs."""

from __future__ import annotations

import argparse
import json

import database
from sync_jobs import enqueue_due_sync_jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Enqueue due durable Triage source-sync jobs.")
    parser.add_argument("--run-once", action="store_true", help="Enqueue currently due jobs and exit.")
    arguments = parser.parse_args()
    if not arguments.run_once:
        parser.error("--run-once is required.")
    if not database.USING_POSTGRES:
        print(json.dumps({"status": "blocked", "reason": "External scheduling requires hosted PostgreSQL."}))
        return 0
    print(json.dumps(enqueue_due_sync_jobs()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
