# Triage v2 External Scheduling

## Objective

Step 6 moves scheduling out of the FastAPI process. A short-lived external cron job
invokes `sync_scheduler.py --run-once`, which only creates idempotent `sync_jobs`
rows. It does not fetch a provider, classify a message, or make an external change.

## Scheduling behavior

- Enabled hosted Gmail/Classroom connections are considered at their configured
  interval (minimum 15 minutes).
- Each connection maps to a deterministic UTC time-window idempotency key. Repeated,
  delayed, or overlapping cron calls in the same window return the existing job.
- Paused connections are excluded, and pausing cancels queued or leased jobs.
- The scheduler command refuses to run outside hosted PostgreSQL mode.
- A separate worker service later claims jobs; no API route performs a source sync.

## Railway setup

Create a separate Railway service from the same repository and provide its hosted
PostgreSQL connection variable (`DATABASE_URL`). It does not need Google OAuth,
VAPID, or browser-session secrets because it only enqueues work. Set its start
command to:

```text
cd backend && python sync_scheduler.py --run-once
```

Set its Cron Schedule to `*/5 * * * *` (UTC). Railway cron services should run a
short-lived command and exit; its minimum cadence is five minutes. The five-minute
cron is safe because each source connection still creates only one job per own
15-minute-or-longer interval.

Do not point the cron service at the web server command, enable APScheduler in the
API process, or call a source-sync HTTP route. The scheduler and API remain separate
failure domains.

## Worker rollout boundary

This step schedules queue entries only. Do not configure a cron worker handler until
the connector contract, evaluation exit gate, and autonomous-ingestion task are
complete. When that is ready, deploy a second short-lived service using:

```text
cd backend && python sync_worker.py --run-once --worker-id railway-worker --handler package.module:function
```

The handler name is intentionally a placeholder today; no source executor exists in
this task.

## Staging checks

1. Use a separate staging Postgres database and at least one enabled test connection.
2. Trigger the scheduler command twice inside one connection interval; verify one
   `sync_jobs` row per workspace/source/window.
3. Pause the connection, trigger it again, and verify no new job is queued.
4. Confirm the cron process exits after enqueueing and that the API process received
   no source-sync request.
