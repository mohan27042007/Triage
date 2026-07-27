"""Explicit, opt-in retention command for operational records only."""

from __future__ import annotations

import argparse
import json
import os

import database


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge expired Triage operational records.")
    parser.add_argument("--run-once", action="store_true", help="Purge configured expired operational records and exit.")
    arguments = parser.parse_args()
    if not arguments.run_once:
        parser.error("--run-once is required.")
    if os.getenv("RETENTION_MAINTENANCE_ENABLED", "").lower() != "true":
        print(json.dumps({"status": "blocked", "reason": "Retention maintenance is disabled."}))
        return 0
    if not database.USING_POSTGRES:
        print(json.dumps({"status": "blocked", "reason": "Retention maintenance requires hosted PostgreSQL."}))
        return 0
    retention_days = int(os.getenv("OPERATIONAL_RECORD_RETENTION_DAYS", "90"))
    print(json.dumps(database.purge_expired_operational_records(retention_days)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
