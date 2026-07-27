# Triage v2 Audit, Retention, and Kill Switch

## Objective

Step 10 adds privacy-minimized operational evidence, a workspace emergency stop for
autonomous work, and an explicitly enabled maintenance command for operational-record
retention. It does not delete source items, attachments, credentials, accounts, or
browser-only form data.

## Audit events

`audit_events` is append-only in application behavior and records only workspace and
owner identifiers, actor type, event type, item/job identifiers, outcome, stable error
code, and timestamp. It intentionally has no message body, attachment bytes, provider
response, credential, URL, recipient, or generated draft column.

`GET /workspace/audit-events` returns the signed-in workspace's redacted outcomes.

## Workspace kill switch

`POST /workspace/automation` with `{"automation_paused": true}` immediately cancels
queued or leased jobs for the current hosted workspace. The scheduler excludes paused
workspaces, job claims exclude them, and the Google worker checks once more before
reading a provider. Manual user-requested sync remains available so a user can recover
or inspect their connection.

Set `{"automation_paused": false}` only after the incident runbook owner confirms the
workspace is safe to resume. Every toggle produces a redacted user audit event.

## Retention

`retention_maintenance.py --run-once` deletes only records older than the configured
period from `audit_events`, `notification_deliveries`, and terminal `sync_jobs`.
Default target: 90 days. It refuses to run unless both of these hosted service
variables are set:

```text
RETENTION_MAINTENANCE_ENABLED=true
OPERATIONAL_RECORD_RETENTION_DAYS=90
```

Before any retention run: obtain separate approval, verify a current Postgres backup,
run it in staging first, and record the deleted-count output. Do not configure a cron
service for this command until that approval is explicit.

## Staging verification

1. Deploy migrations to a separate staging Postgres database.
2. Enable a test workspace's kill switch and verify its queued jobs become cancelled.
3. Verify the scheduler and worker do not claim new jobs for that workspace.
4. Check `/workspace/audit-events` while signed in; confirm it contains outcome/error
   codes but no message content or credentials.
5. With a disposable staging database and backup, run the retention command once and
   confirm only old operational records were deleted.
