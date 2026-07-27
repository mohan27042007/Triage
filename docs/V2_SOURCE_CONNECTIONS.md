# Triage v2 Source Connections

## Objective

Step 3 persists connection configuration and health separately from individual sync
outcomes. It prepares Gmail and Google Classroom for future worker-based syncing
without enabling autonomous sync in this step.

## Stored connection state

Each source connection records its owner and workspace, provider credential reference,
enabled/paused state, selected channels, minimum 15-minute sync interval, opaque
provider cursor field, consecutive failures, and last attempt/success/error.

The record stores only an opaque reference such as `google-connection:<user-id>`.
OAuth credentials remain in the existing encrypted `google_connections` store and
are never returned by the connection API.

## Current API behavior

- `GET /sources/status` now returns source sync outcomes plus connection health.
- `POST /sources/gmail/connection/enable` and the Classroom equivalent save or resume
  a read-only Google connection after Google OAuth is available.
- `POST /sources/gmail/connection/pause` and the Classroom equivalent pause future
  sync attempts without deleting the saved configuration or health history.
- Manual Gmail/Classroom sync refuses to run while its connection is paused. The
  current UI can connect, pause, resume, and display the server-persisted status.

## Migration and safety

The hosted migration creates `source_connections` after personal workspaces exist.
It backfills a connection record from existing Gmail/Classroom source-sync status
only when that record already has a workspace. No provider credential, token, or raw
message content is copied into the new table.

This task does not schedule background work, consume provider cursors, add Slack or
Teams, or change source-item deduplication. Those belong to later v2 tasks.
