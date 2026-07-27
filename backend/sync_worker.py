"""Operational entry point for a single leased sync-worker iteration."""

from __future__ import annotations

import argparse
import importlib
import json
from typing import Any

from sync_jobs import run_once


def _load_executor(target: str):
    module_name, separator, attribute = target.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("Handler must use module:function format.")
    executor = getattr(importlib.import_module(module_name), attribute, None)
    if not callable(executor):
        raise ValueError("Worker handler must be callable.")
    return executor


def main() -> int:
    parser = argparse.ArgumentParser(description="Claim and run one durable Triage sync job.")
    parser.add_argument("--run-once", action="store_true", help="Claim and execute at most one job.")
    parser.add_argument("--worker-id", default="triage-worker", help="Stable identifier for this worker process.")
    parser.add_argument("--handler", help="Explicit executor in module:function form.")
    arguments = parser.parse_args()
    if not arguments.run_once:
        parser.error("--run-once is required.")
    if not arguments.handler:
        print(json.dumps({"status": "blocked", "reason": "A connector handler is not configured."}))
        return 0
    try:
        result: dict[str, Any] = run_once(_load_executor(arguments.handler), worker_id=arguments.worker_id)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
