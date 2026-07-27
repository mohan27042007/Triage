# Triage v2 PostgreSQL Migration Framework

## Objective

Step 2 replaces bootstrap-only hosted schema setup with ordered, recorded PostgreSQL
migrations. It keeps local SQLite initialization unchanged and never recreates,
resets, or overwrites a database.

## How it works

- `backend/postgres_migrations.py` owns ordered core and hosted migration lists.
- Startup obtains a PostgreSQL transaction-scoped advisory lock, so concurrent web
  instances cannot apply the same migration twice.
- Applied migration IDs are stored in `postgres_schema_migrations` only after their
  migration function succeeds. A failed migration is not marked complete and the
  surrounding database transaction rolls back.
- Existing hosted schemas upgrade safely through additive table/column changes and
  idempotent backfills. The source-dedupe migration replaces obsolete indexes only;
  it never deletes or rewrites item data.

## Deployment procedure

1. Back up the production Postgres database using the hosting provider's documented
   backup process. Do not run a destructive migration without separate approval.
2. Deploy the release to staging with its own Postgres database first.
3. Start one application instance and inspect the migration ledger:

```sql
SELECT id, applied_at FROM postgres_schema_migrations ORDER BY applied_at, id;
```

4. Verify the Step 1 workspace checks in `docs/V2_WORKSPACE_FOUNDATION.md`.
5. Confirm normal hosted sign-in, source-status reads, and account export before
   allowing additional instances to start.
6. Repeat the same checks in production during a maintenance window.

## Failure and rollback procedure

- A startup migration failure should leave no migration ledger entry for the failed
  change. Keep the service stopped, inspect the error, and correct the migration in
  a new release.
- Do not manually delete ledger rows, drop tables, or restore an older schema over
  newer user data.
- If application code must be rolled back, deploy the last compatible release; all
  current migrations are additive and therefore safe for this forward-only rollback.
- Restore a backup only for a separately approved data-recovery incident, following
  the provider runbook and the project's database-safety rules.

## Current migration inventory

| ID | Scope |
| --- | --- |
| `2026-07-26-core-schema-v1` | Core Triage records. |
| `2026-07-27-core-workspace-columns-v1` | Nullable workspace compatibility columns for existing hosted records. |
| `2026-07-26-hosted-auth-schema-v1` | Hosted users, OAuth credentials, sessions, push subscriptions, and reminder deliveries. |
| `2026-07-27-personal-workspaces-v1` | Personal workspaces, memberships, and idempotent workspace backfill. |
| `2026-07-27-source-connections-v1` | Workspace-scoped Gmail/Classroom connection configuration and health. |
| `2026-07-27-workspace-source-dedupe-v1` | Replaces obsolete item indexes with provider-aware workspace deduplication. |
| `2026-07-27-workspace-sync-jobs-v1` | Durable workspace/source sync jobs with idempotency keys, leases, and retry state. |
