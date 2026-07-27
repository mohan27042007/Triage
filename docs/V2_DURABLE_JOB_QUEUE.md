# Triage v2 Durable Job Queue

## Objective

Step 5 adds a durable `sync_jobs` ledger so future source runs can survive process
restarts and multiple worker replicas. It deliberately does **not** schedule or run
Gmail/Classroom ingestion yet; that remains a later autonomy and connector task.

## Job model

Each job is scoped to a hosted workspace and source, with a deterministic
idempotency key. It records `queued`, `running`, `succeeded`, `failed`, or
`cancelled` state, attempt count, bounded maximum attempts, availability time, lease
token/expiry, a structured outcome, and a redacted error code.

- PostgreSQL claims one job with `FOR UPDATE SKIP LOCKED` inside one statement.
- A worker lease expires after five minutes by default. A replacement worker may
  reclaim expired work, incrementing its attempt count.
- Failures retry with bounded exponential backoff and jitter. The fifth failed
  attempt is terminal.
- Pausing a source cancels its queued or leased jobs, and a claim also requires its
  source connection to be enabled.

The job outcome is limited to 1,000 serialized characters. Raw messages,
attachments, credentials, and exception text must never be placed in it; record a
stable error code instead.

## Worker command

The generic runner executes at most one leased job:

```powershell
cd backend
python sync_worker.py --run-once --worker-id worker-a --handler package.module:function
```

The handler is explicit rather than built in. Without `--handler`, the command exits
without claiming work. The queue contains no source handler; scheduling is configured
separately and still cannot autonomously sync before the later connector safety gate.

## Deployment checks

1. Back up Postgres and deploy to staging first.
2. Confirm the new migration is recorded:

```sql
SELECT id FROM postgres_schema_migrations
WHERE id = '2026-07-27-workspace-sync-jobs-v1';
```

3. Enqueue one staging job twice with the same workspace, source, and idempotency
   key; confirm one row exists.
4. Run two worker replicas and verify only one receives the lease. Stop it before
   lease expiry, then verify the other worker can reclaim the job afterward.

No project database is opened or modified by the Step 5 test suite.
