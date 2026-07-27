# Triage v2 Policy Routing and Review

## Objective

Step 9 adds deterministic, persisted review routing to every newly created item. It
does not use model confidence as a safety gate and does not authorize any external
action.

## Current deterministic rules

An item receives `review_required` and stable `review_reasons` when it has:

- an Obligation without an explicit deadline;
- both required/mandatory and optional/not-required language; or
- an obligation that asks for an external action (including a detected poll/form).

`draft_eligible` is true only for an Obligation detected as a poll/form. Eligibility
means a copy-only draft may be prepared through the existing human-review flow; it
never grants permission to send, submit, pay, vote, register, or fill an external
form.

## Explicit limitation

The current normalized Gmail/Classroom item contract does not retain sender identity,
so an unfamiliar-sender rule is deliberately **not** fabricated. Add that rule only
after connector metadata includes a privacy-reviewed sender identity and allowlist.

## Persistence and migration

New item records store `review_required`, JSON `review_reasons`, and `draft_eligible`.
PostgreSQL migration `2026-07-27-policy-routing-v1` adds the fields with safe defaults
and does not rewrite existing items. Existing records remain readable with no inferred
review state.

## Manual verification

No new secret, sign-in, scheduler, or worker configuration is required. After a
staging deployment, ingest a synthetic obligation without a deadline and verify the
item API response includes the expected review fields. Test a poll/form draft through
the existing approval UI, and confirm it remains copy-only.
