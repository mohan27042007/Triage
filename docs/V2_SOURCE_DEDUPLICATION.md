# Triage v2 Source Deduplication

## Objective

Step 4 makes imported-item identity provider-aware and workspace-scoped. Provider
IDs are not globally unique: a Gmail message ID and a Classroom item ID may have
the same text. The hosted identity key is therefore:

```text
(workspace_id, source, source_id)
```

Local/demo records that have no workspace retain a compatible identity key:

```text
(owner_id, source, source_id) where workspace_id is NULL
```

Manual items without a `source_id` are unaffected.

## Implementation

- `create_item` first looks up an existing record with the complete identity key.
- The database index enforces the same key, and the insert uses `ON CONFLICT DO
  NOTHING` as a concurrency backstop.
- Gmail and Classroom sync routes pass their explicit provider name and request
  workspace to the lookup.
- Migration `2026-07-27-workspace-source-dedupe-v1` removes only the two obsolete
  indexes and creates the two replacement partial unique indexes. It does not
  delete, rewrite, reset, or recreate item data. Before changing indexes, it checks
  for legacy duplicate workspace/provider/source IDs and stops transactionally with
  an actionable error if any exist.

## Deployment checks

1. Back up Postgres using the provider-approved backup procedure.
2. Apply and inspect the migration in staging before production:

```sql
SELECT id FROM postgres_schema_migrations
WHERE id = '2026-07-27-workspace-source-dedupe-v1';

SELECT indexname FROM pg_indexes
WHERE tablename = 'items'
  AND indexname IN ('idx_items_workspace_source_id', 'idx_items_local_owner_source_id');
```

3. Verify that an identical Gmail source ID imports once in a workspace, while an
   identical Classroom source ID remains a separate record.

No project database is opened or modified by the Step 4 tests.
