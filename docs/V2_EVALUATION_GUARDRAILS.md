# Triage v2 Evaluation and Operational Guardrails

## Purpose and scope

This is Step 0 of the v2 plan. It establishes evidence and operating rules before
Triage starts autonomous source syncing. It does not enable autonomous behavior,
change the classifier prompt, write to the database, or change approval behavior.

Triage remains a deterministic pipeline with model judgment inside classification.
It does not become a multi-agent planner and it never sends, submits, posts, or
changes an external system without explicit user approval.

## Classification evaluation gate

`backend/evaluations/corpus_v1.json` is a versioned, synthetic-only regression
corpus. It contains no user messages, student records, credentials, attachments,
or provider identifiers. Do not add real user content to the repository.

Run the committed structural checks from the backend directory:

```powershell
cd backend
..\.venv\Scripts\python.exe -m unittest test_evaluation.py
```

Run a live model evaluation only after setting `OPENAI_API_KEY`; it sends only the
synthetic corpus to the configured OpenAI model:

```powershell
cd backend
..\.venv\Scripts\python.exe run_classification_evaluation.py
```

Autonomous classification is blocked until the current corpus meets all gates:

| Signal | Minimum / maximum | Reason |
| --- | --- | --- |
| Category accuracy | >= 90% | Detect broad classification regressions. |
| Obligation recall | >= 95% | Missing obligations is the primary product risk. |
| Must-detect obligation recall | 100% | Critical forms, payments, attendance, and deadlines cannot be missed. |
| False-obligation rate | <= 10% | Avoid overwhelming students with false urgency. |
| Invalid category output | 0 | Structured output must remain machine-safe. |

This corpus is a release gate, not a claim of statistical production quality. Before
expanding autonomous access, add a separately stored, consented, de-identified
evaluation set, record its provenance and reviewer, and version each change.

## Environment separation and secrets

| Environment | Purpose | Data and access rules |
| --- | --- | --- |
| Local demo | Development and UI demonstrations | SQLite, local OAuth fallback, synthetic/demo data only when demonstrating. |
| Staging | Integration and worker rehearsal | Separate Postgres, OAuth clients, VAPID keys, bucket, and OpenAI project/key. No production user data. |
| Production | Opted-in user operation | Hosted Postgres, encrypted credentials, private object storage, least-privilege source scopes, monitored jobs. |

Never reuse production OAuth clients, database URLs, encryption keys, VAPID private
keys, source tokens, or OpenAI API keys in local or staging. Store all secrets in
the host's secret manager; `.env` files, `credentials.json`, `token.json`, databases,
and archive directories remain ignored by Git.

### Secret inventory

| Secret | Used for | Storage and rotation rule |
| --- | --- | --- |
| `OPENAI_API_KEY` | Classification and study planning | Separate key/project per environment; revoke on exposure. |
| `DATABASE_URL` | Hosted Postgres | Host secret manager; rotate on provider compromise. |
| `GOOGLE_CLIENT_SECRET` | Hosted Google OAuth | Host secret manager; rotate if exposed or client is replaced. |
| `OAUTH_TOKEN_ENCRYPTION_KEY` | Fernet encryption for hosted Google credentials and push subscriptions | Generate and retain in a managed secret store; rotate with decrypt-old/encrypt-new migration before retiring the old key. |
| `VAPID_PRIVATE_KEY` | Web Push signing | Production-only secret; rotate by issuing a new public/private pair and requiring re-subscription. |
| `REMINDER_DISPATCH_SECRET` | Scheduler-facing reminder endpoint | Rotate after exposure and update the scheduler atomically. |
| S3-compatible access keys | Private attachment archive | Scope to the Triage bucket/prefix; rotate and audit provider access logs. |

## Retention and deletion policy

The following is the v2 policy target. Enforcement work belongs with the audit and
privacy-control task; do not represent it as implemented until tests prove it.

| Data class | Target retention | Deletion path |
| --- | --- | --- |
| Raw source text and retained attachments | User-controlled, with a documented default before production launch | Per-item/archive deletion and account deletion. |
| OAuth states and expired sessions | Delete at expiry or within 24 hours | Automatic cleanup job. |
| Sync jobs and redacted audit events | 90 days by default, configurable by workspace policy | Scheduled expiry plus workspace deletion. |
| Push subscriptions | Until unsubscribe, endpoint invalidation, or account deletion | Existing unsubscribe/invalid-endpoint handling; account deletion later. |
| Evaluation data | Synthetic corpus is versioned in Git; consented private data stays outside the repo | Remove from restricted evaluation store on consent withdrawal. |

## Incident and operating runbook

1. **Stop:** enable the affected workspace's automation kill switch; it cancels its
   queued/leased jobs and blocks scheduler/worker collection. Also disable the
   worker/scheduler deployment if broader containment is required.
2. **Contain:** revoke affected OAuth tokens, API keys, or storage credentials;
   do not retry a suspected compromised connection.
3. **Preserve minimal evidence:** record timestamps, workspace/source identifiers,
   redacted error codes, and actions taken. Do not copy message bodies or credentials
   into tickets or logs.
4. **Recover:** rotate exposed secrets, repair the connection, run the synthetic
   evaluation gate, and resume only after an explicit owner check.
5. **Review:** document root cause, affected scope, data exposure assessment, and
   preventive change before re-enabling broad automation.

## Step 0 exit criteria

- Synthetic corpus and structural tests pass.
- A live synthetic evaluation has been run and recorded before enabling autonomous
  classification.
- The above secret inventory, environment separation, retention policy, and incident
  runbook have an assigned owner before a worker is deployed.
- No autonomous external action is introduced by this step.
