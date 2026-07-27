# Triage v2 Connector Abstraction

## Objective

Step 7 wraps the existing read-only Gmail and Classroom fetchers behind one narrow
connector contract. It preserves current manual-sync behavior while establishing the
boundary needed by a future leased worker.

## Contract

`backend/source_connectors.py` defines:

- `SourceConnection`: non-secret source, owner, workspace, selected-channel, and
  opaque-cursor state for one collection attempt.
- `FetchResult`: normalized items and a next cursor that is returned but never
  committed by the connector.
- `ConnectionHealth`: an explicit result for a lightweight provider/token check.
- `SourceConnector`: `fetch_changes` and `validate_connection` methods.

Gmail and Classroom adapters preserve stable source IDs, plain text, and attachment
bytes already supplied by their existing fetchers. Their validation methods perform
read-only provider requests only when explicitly called.

## Cursor boundary

The current Gmail/Classroom fetch functions do not expose an opaque provider cursor,
so the adapters preserve the passed cursor unchanged and the manual routes pass
`None`. This step intentionally does not advance or persist a cursor. A later worker
task must add provider-specific paging/checkpoints and commit each next cursor only
after its items are durably handled.

## Current behavior and safety

- `POST /sources/gmail/sync` and `POST /sources/classroom/sync` now collect through
  the connector registry, then retain their existing classify/archive/dedupe flow.
- Collection remains user-requested, read-only, and paused-source protected.
- No Slack or Teams connector, background handler, cursor mutation, scheduler
  change, or automatic external action is introduced here.

## Manual verification after deployment

No new configuration is required for this code change. In staging or a manually
verified hosted deployment:

1. Sign in with an already configured Google account.
2. Enable Gmail and Classroom through the source UI if they are not already enabled.
3. Run each manual sync once and verify that its items appear, a second run skips
   duplicates, and pause/resume still behaves as before.
4. Do not enable a worker handler or cron service for source execution yet.
