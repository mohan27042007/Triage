# Triage v2 Autonomous Google Pilot

## Objective

Step 8 adds the first opt-in worker handler for Gmail and Classroom. It can only
read selected Google sources, classify them, archive allowed attachments, and create
inert Triage records. It never sends mail, posts to Classroom, submits forms, fills
external pages, or marks any external task complete.

## Enforced pilot gates

`autonomous_google_worker:execute_sync_job` refuses a job unless all conditions hold:

1. `AUTONOMOUS_GOOGLE_SYNC_ENABLED=true`.
2. The job workspace is listed in `AUTONOMOUS_GOOGLE_PILOT_WORKSPACE_IDS`.
3. `AUTONOMOUS_EVALUATION_METRICS_JSON` parses and meets the committed evaluation
   thresholds (90% accuracy, 95% obligation recall, 100% must-detect recall, at most
   10% false-obligation rate, and no invalid outputs).
4. The stored source connection belongs to that workspace, is enabled, and has an
   explicit source selection.

Jobs that fail a gate retain a stable, redacted error code and use the queue's bounded
retry behavior. They do not include source content or provider exception text.

## Source selection and circuit breaker

- Gmail pilot connections must use `selected_channels: ["inbox"]`.
- Classroom pilot connections must use `selected_channels` containing the permitted
  Google Classroom course IDs. The connector filters to those courses.
- Five consecutive worker collection/classification failures automatically pause the
  connection and cancel its queued or leased jobs. A user must explicitly resume it.

Current Gmail/Classroom fetchers still do not expose an opaque provider cursor. The
worker passes through the stored cursor without advancing it; source-item dedupe makes
the repeated read safe until provider checkpoint support is added.

## Staging-only rollout

1. Create a separate staging Postgres deployment, OAuth client, OpenAI key, encryption
   key, and archive storage. Do not use production users, credentials, or data.
2. Run `python run_classification_evaluation.py` in `backend` with the staging OpenAI
   key. Continue only if it prints `Evaluation gate passed.` Record the printed JSON.
3. Add these staging service variables, replacing the example workspace ID and metrics
   with the actual passing evaluation output:

```text
AUTONOMOUS_GOOGLE_SYNC_ENABLED=true
AUTONOMOUS_GOOGLE_PILOT_WORKSPACE_IDS=123
AUTONOMOUS_EVALUATION_METRICS_JSON={"accuracy":0.95,"obligation_recall":1.0,"must_detect_recall":1.0,"false_obligation_rate":0.05,"invalid_outputs":[]}
```

4. Sign in with a staging Google account. Enable the pilot source with an explicit
   selection through the authenticated connection endpoint:

```text
POST /sources/gmail/connection/enable
{"selected_channels":["inbox"],"sync_interval_minutes":30}
```

For Classroom, replace `inbox` with one or more actual course IDs. A Google Classroom
course URL contains its course ID; do not use an all-courses selection for the pilot.

5. Create a separate short-lived worker service using the same **staging**
`DATABASE_URL` and its start command:

```text
cd backend && python sync_worker.py --run-once --worker-id staging-google-pilot --handler autonomous_google_worker:execute_sync_job
```

6. Keep the scheduler and worker disabled until the previous checks are complete.
Then run one staged job and verify processed/skipped counts, duplicate handling, a
deliberate provider failure/retry, and source pause after five failures.

## Production boundary

This is a limited pilot mechanism, not permission to enable every workspace. Before
production use, repeat staging checks, use an explicitly consenting workspace ID,
assign a runbook owner, and retain a human approval path for every consequential
action. Do not broaden the allowlist or configure a production worker without a
separate approval.
