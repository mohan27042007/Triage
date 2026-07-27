# Triage v2 Personal Workspace Foundation

## Objective

Step 1 adds a personal workspace for every hosted account without changing current
local-demo behavior. It is the tenancy seam needed before Triage adds background
workers, additional source connections, professional defaults, or organization
memberships.

## What changes

- Hosted startup creates `workspaces` and `workspace_memberships` if they do not
  already exist.
- Every existing hosted user is backfilled exactly once into a `personal` workspace
  and receives an `individual` membership.
- New Google OAuth users receive the same workspace in the authorization transaction.
- `workspace_id` is added as a nullable, compatibility field to items, study plans,
  pending actions, assignment scaffolds, and source-sync status. Existing `owner_id`
  query scoping remains in force during this transition.
- Hosted requests resolve a personal workspace before they perform an authenticated
  action. Local demo requests retain `workspace_id=None`.

## Safety and migration behavior

The workspace foundation is additive only: it uses `CREATE TABLE IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS`, `INSERT ... ON CONFLICT DO NOTHING`, and `UPDATE` only
where `workspace_id` is null. It does not delete, recreate, reset, or overwrite a
database. No foreign key is attached to the new compatibility columns yet because
the upcoming migration-framework task will consolidate versioned hosted migrations.

## Hosted deployment verification

Run these checks against a **staging Postgres database first**, after backing up any
production database according to the hosting provider's process:

```sql
\d workspaces
\d workspace_memberships
SELECT COUNT(*) AS hosted_users FROM users;
SELECT COUNT(*) AS personal_workspaces FROM workspaces WHERE kind = 'personal';
SELECT COUNT(*) AS individual_memberships FROM workspace_memberships WHERE role = 'individual';
SELECT COUNT(*) AS unassigned_items FROM items WHERE workspace_id IS NULL;
```

For existing hosted users, the first three counts should match. Investigate any
unassigned records before relying on workspace-based reads; local-demo rows are
expected to remain outside the hosted workspace model.

## Current boundary

This task does not add a workspace switcher, shared organization workspaces,
invitations, source-connection records, autonomous jobs, or workspace-based read
queries. Those follow in later v2 tasks after the migration framework is in place.
