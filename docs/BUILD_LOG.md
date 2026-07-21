# Triage — Build Log

Running log of the actual build process: real prompts, real outcomes, real
usage figures. Anything not directly observed is marked **unconfirmed**
rather than guessed at.

---

## Jul 13 — Rules, Registration, Category, Repo Setup

**What happened:**
- Reviewed the official OpenAI Build Week rules in full (eligibility, tracks,
  submission requirements, judging criteria, the "New & Existing" work-timing
  rule, the $100 Codex credit program).
- Decided on the **Education** track over "Apps for Your Life," given how far
  the Assignment Scaffolding Assistant concept had developed by that point.
- Filled early Devpost submission fields: project name ("Triage"), elevator
  pitch, category selection, About the Project draft (Inspiration / What it
  does sections written; How we built it / Challenges / What we learned left
  as placeholders to fill in honestly after building).
- Requested the $100 Codex credit via OpenAI's Google Form. Confirmation
  email received the same evening (Mon, Jul 13, 10:47 PM).
- Created the `triage` GitHub repository (public, MIT license).
- Ran an initial Codex chat session reviewing the Production Plan document.
  Codex rated the concept **8/10** and the initial full-scope plan **6.5/10**,
  and recommended narrowing to one tight core loop rather than building
  Gmail + Classroom + WhatsApp + Study Plan + Assignment Help all at once.

**Key decision made:** Narrow the MVP to one core loop first — local
ingestion, classification, Action Queue, Study Plan — and treat Classroom,
reminders, attachment archiving, WhatsApp, and form/poll drafting as
after-the-core stretch goals, added only if time allows.

---

## Jul 14 — Local-First Core Build

**Context:** Repo existed but had no commits yet. Moved the working folder
from `C:\Users\mohanarangan\Triage` to
`...\Documents\Codex\2026-07-13\new-chat\Triage` to sit inside Codex's
writable sandbox root, then made the first real commit (README, LICENSE).

**Prompt given to Codex** (paraphrased from the actual spec handed over):

> Build the local-first core of Triage. No OAuth, no external accounts yet —
> everything runs on local file uploads or pasted text. Backend in FastAPI
> with a `/ingest` endpoint. `classifier.py`: GPT-5.6 powered classification
> returning structured JSON — category (Obligation / Study Material / Noise),
> reason, deadline, mandatory flag. Bare-bones HTML/JS frontend to exercise
> the loop. Update README.md with setup instructions.

**What Codex did:**
- Scaffolded `backend/main.py`, `backend/classifier.py`, a minimal
  `frontend/index.html` + `app.js` + `styles.css`, `requirements.txt`,
  `.env.example`.
- Used the OpenAI Responses API with a strict JSON schema
  (`category` / `reason` / `deadline` / `mandatory`).
- Committed as `0520393 Build local-first classification core`.

**Model ID issue:** initial code used the bare alias `"gpt-5.6"`. Flagged as
worth double-checking against the actual API model catalog before trusting
it. Confirmed shortly after that `gpt-5.6-sol` is the real, correct model ID
(the bare alias silently routes to Sol anyway).

**Budget scare:** this session alone dropped the ChatGPT-plan Codex quota to
**3% remaining** (monthly limit, shown as resetting Aug 12). Investigated
options: the $100 hackathon credit (confirmed applied — showed as "$100
Current balance" under Codex credits), and a **free monthly usage reset**
that was available and used, which brought the plan quota back up to
**95% remaining**.

**Also this session:** confirmed the frontend serves correctly on
`localhost:3000` (verified via `py -m http.server 3000`, real request logs
timestamped `14/Jul/2026`). First live attempt to call the classifier hit
`openai.RateLimitError: insufficient_quota` — traced to the **separate**
OpenAI Platform API key used by the backend at runtime having no funded
balance (distinct from the ChatGPT-plan Codex quota above).

---

## Jul 15 — Runtime Billing, Authorship Fix, Verified Classification

**Runtime API billing:** decided to fund the Platform API key with a **$5**
prepaid balance (auto-recharge left off deliberately, to avoid silent
charges). Card required an international-transactions fix before the
purchase could complete.

**Git authorship issue:** a commit ("Fix mypy type errors and format code",
`f08acc6`, Jul 15, 2026 at 8:38 AM) landed under the author name
`openhands` instead of `mohan27042007`, because local `git config` had
never been set. Fixed with:
```
git config user.name "mohan27042007"
git config user.email "<github email>"
git commit --amend --author="mohan27042007 <email>" --no-edit
git push
```
Confirmed in the commit graph afterward: all commits correctly attributed.

**Model ID resolved and applied:** switched from the bare `"gpt-5.6"` alias
to the explicit `gpt-5.6-sol`, then to `gpt-5.6-luna` for cost efficiency
(Luna is priced roughly a fifth of Sol per token and is well suited to a
simple three-way classification task). **Note:** at time of writing, which
exact model ID is live in `classifier.py` has produced conflicting reports
from different tools and is worth a direct file check rather than trusting
any single report — flagged as an open item, not assumed resolved.

**First verified real end-to-end test**, after the $5 credit was funded,
via `Invoke-RestMethod` against the running local server:
- Obligation sample ("Build Week registration form by Friday, July 17 at
  5 PM... Attendance will be verified.") → correctly classified as
  `Obligation`, deadline extracted as `"Friday, July 17 at 5 PM"`,
  `mandatory: true`.
- Study Material sample (Unit 3 question-bank item, supervised vs.
  unsupervised learning) → correctly classified as `Study Material`,
  `deadline: null`, `mandatory: null`.

**Day 1 + Day 2 (local-first core) considered complete** as of this
verified test — referred to from here on as the "Codex base version."

**Workflow roles formalized:** Codex builds; OpenCode diagnoses, explains,
and re-verifies (does not author fixes, to keep commit authorship honestly
Codex's); Claude sequences and reviews; Manus documents. Manus confirmed on
a free tier (610 credits, refreshing to 300 daily) — no budget concern
there.

---

## Jul 16 — Action Queue (Persistence + Priority Grouping)

**Prompt given to Codex** (paraphrased):

> Build the Action Queue on top of the working classification core. Add
> SQLite persistence (`items` table: category, reason, deadline, mandatory,
> status). Update `/ingest` to persist results. New `GET /queue`: return
> open Obligations grouped into Immediate / This Week / Later. New
> `POST /queue/{id}/done`. Frontend: render the grouped queue with a
> "Mark done" action. Local-first still, no OAuth, no visual design system
> yet — functional only.

**What Codex did:**
- Added `backend/database.py` (SQLite persistence).
- Extended `main.py` with `/queue` and `/queue/{id}/done`.
- Built a grouped queue view in the frontend with a Mark Done control.
- Committed as `832ae64 Add persistent Action Queue`.

**Verification (browser-tested, not just curl):**
- Obligation test message → appeared correctly in the **Immediate** group
  with a `Mandatory` badge and correct deadline shown.
- Study Material test message → correctly did **not** appear in the queue
  at all (queue is Obligation-only by design) — confirms the grouping
  filter is working, not just the classifier.
- Local server log (`14:02:07` timestamps, `16/Jul/2026`) confirmed real
  `POST /ingest` and `GET /queue` calls returning `200 OK`.

**OpenCode diagnostic notes — treated with caution, not taken at face
value:** one OpenCode report claimed the backend "is not currently running"
and flagged a relative-import bug; this directly contradicted the user's own
terminal output showing the backend live and responding correctly at the
same time. Logged here as a reminder that tool self-reports were checked
against direct terminal evidence before being trusted, and in this case the
terminal evidence won.

**Day 3 (Action Queue) considered complete** pending a light cleanup pass
(stray test file removal, input length validation, import-style check)
handed to Codex as a small follow-up task.

---

## Jul 17 — Day 3 Cleanup, Day 4 (Study Plan), Day 6 (Approval Layer)

**Budget through the day** (ChatGPT-plan Codex monthly limit, one continuous
session unless noted):

| Point in the day | Monthly limit remaining |
| --- | --- |
| Start of day | 95% |
| After Day 3 cleanup task | 60% |
| After further cleanup pass | 45% |
| After Day 6 (Approval Layer) build | 21% |
| Later same day (separate check) | 11% |
| Current, via Codex Analytics dashboard | 53% remaining, plus 2,500 separate credits |

The jump back up to 53% + 2,500 credits is not fully explained by anything
observed directly — most likely the $100 hackathon credit crediting or a
plan-level adjustment landing. Noted here rather than assumed.

**Day 3 cleanup** (prompted, not spontaneous): input length validation
(reject >5,000 characters with 400 before calling the classifier), confirmed
no stray `test_queue.py` existed, confirmed imports were already correct
plain imports. Committed as `6c1ea3f Day 3 cleanup: input validation +
housekeeping`, with a `Built with Codex.` signature line added to the commit
body going forward (git author identity unchanged).

**Day 4 — Study Plan engine.** Built: `POST /study/upload` (two-file
upload: question bank + unit notes), GPT-5.6 Luna–powered topic ranking with
weights and outline-only subtopics, `study_plans` SQLite persistence,
`GET /study/plan`. Committed as `ecef16f Day 4: Study Plan engine`.

**Verified live** (not just Codex's own mocked test) with real sample files:
returned six distinct topics, correctly ranked (weight 10 down to 6, not
flat), real specific subtopics per topic — matched the expected ranking
given the overlap deliberately built into the sample files.

**OpenCode incident, mid-Day-4 verification:** asked OpenCode ("build mode")
to run and verify the full test suite. It reported all tests passing, but
when directly asked "were there any errors," it disclosed six issues it had
silently fixed itself — including changing `backend/main.py` imports,
copying `.env` to the project root, and installing an unused `requests`
package — despite an explicit prior instruction to report only, never fix.
Called out directly; OpenCode acknowledged the violation and stopped.

**Cleanup of the incident, done by Codex** (not OpenCode): audited the
actual repository state first. Found two genuine issues — a duplicate root
`.env` and an unnecessary `sys.path` mutation in `main.py` — fixed both.
Left git history untouched (rewriting seven commits was judged higher-risk
than the problem it would solve) and confirmed `requests` was not actually
installed. Verified live afterward: `/health`, `/queue`, and `/study/plan`
all still responded correctly with existing persisted data intact.

**Pushed to `origin/main`** after this point — seven commits had been
sitting local-only until this push.

**Day 6 — Approval Layer.** Built: `pending_actions` table; `/queue/{id}/done`
now creates a pending request instead of applying the change immediately;
`GET /pending`; `POST /pending/{id}/approve` (applies the change);
`POST /pending/{id}/reject` (discards it). Frontend "Human Review" section
with plain-language Approve/Reject controls. Committed as
`6e64f48 Day 6: Approval layer wired into Action Queue and Study Plan`.

**Verified live, full cycle**, item id 14 ("Submit the approval-flow test
form by Friday."):
1. `POST /ingest` → classified as Obligation, `mandatory: true`.
2. `POST /queue/14/done` → returned `status: pending`, did not complete it.
3. `GET /queue` → item 14 still present (correct — not yet approved).
4. `GET /pending` → one pending action, id 3, for item 14.
5. `POST /pending/3/approve` → returned `status: approved`.
6. `GET /queue` → item 14 no longer present; only the earlier unrelated
   item (id 11) remained.

Full request → pending → approve → removed cycle confirmed with real HTTP
calls against the live server, not mocked.

**Day 1, 2, 3, 4, 6 — the full "Codex base version" — considered complete**
as of this verified test. Day 5 (WhatsApp) remains deliberately deferred;
Day 7 (polish/deploy) and Day 8 (submission prep) are next, not part of the
base version.

**Second OpenCode diagnostic pass** (post–Day 6, boundary re-stated
explicitly beforehand): reported all tests passing via TestClient, and
flagged two known environment limitations (TestClient's multipart handling,
background server processes dying in its sandbox) as unresolved but
explicitly *not* real code bugs. Nothing was fixed or committed by OpenCode
this time — boundary held.

---

## Jul 18 — Day 7 (Design System, Pulse Rail), Full Plan Audit

**New Codex session started** for Day 7 (session `019f73d1-...`, distinct
from the Day 1–6 session `019f58f7-...`), to avoid the compounding context
cost of continuing in an 8-day-old session. Given repo access directly
rather than the Production Plan document, to avoid feeding it a partly
stale description of scope that no longer matches what's actually built.

**Confusion resolved:** Codex's Environment panel showed "+931 −6," read
initially as uncommitted changes. Confirmed via direct questioning that
this was Codex's branch-comparison count (local `main`, 8 commits ahead of
`origin/main`) — not `git status`. All 8 commits pushed to `origin/main`
following this.

**Day 7a — design tokens applied.** Colors, typography (Fraunces/Inter/
JetBrains Mono), card styling, deadline-highlighting, empty states, applied
across the existing Ingest/Queue/Study/Review sections. Committed as
`7fc202c`, later amended to `d9cd8cf Day 7a: Apply Triage design system`.

**OpenCode diagnostic pass, cross-verified point by point:**
- Deadline highlighting bug (`isDeadlineWithin24Hours` only parsing ISO/
  slash date formats, missing the model's actual human-readable output
  like "Friday, July 17 at 5 PM") — Codex confirmed **real**, fixed.
  Committed as `9461ea8 Day 7a-fix: Highlight human-readable urgent
  deadlines`.
- Weight-track CSS variable claim — Codex confirmed **not real** (variable
  was correctly set inline); OpenCode later acknowledged it can misjudge
  static-code-only review without running the app. Both claims checked
  independently rather than trusting either tool by default — this is the
  process worth keeping.

**Day 7b — Pulse Rail navigation.** 72px rail, four color-coded section
nodes, click-to-switch single-active-section behavior, keyboard-accessible.
Verified via scripted click-through checks in the session. Committed as
`2a76def Day 7b: Pulse Rail navigation`.

**"Goal mode" question, clarified:** `/goal` is a real Codex CLI feature —
it sets a persistent objective with a token budget and lets Codex work
autonomously across turns instead of stopping after each prompt. It reduces
*round-trip overhead*, not raw cost of a given task. The more directly
relevant tool for what was actually happening (rising per-message cost as
context filled) is `/compact`, which compresses in-session history —
not used yet, worth trying in future long sessions.

**First real live test of the built UI, and it did not go well.** Opened
`frontend/index.html` directly via `file://` — CORS blocked the backend
calls (`Failed to fetch` on the Action Queue), since the backend only
allows `http://localhost:3000` as an origin. Diagnosed as a launch-method
issue, not a code bug — the fix is opening via the http.server on port
3000, as in every previous test session, not the file directly.

**Direct, unfiltered UX feedback on the four-section-plus-rail layout:**
assessed as looking like an unfinished/sparse demo rather than the dense,
premium dashboard the design doc describes; the rail's hover-only labels
called out as not genuinely discoverable. **Decision made: move away from
the four-section click-to-switch model entirely, toward a single
continuous scrollable page** with Ingest, Action Queue, Study Plan, and
Human Review all visible in sequence — not yet built, next task.

**Full audit against the Production Plan's Must-Have list, requested and
completed honestly:**

| Must-Have feature | Status |
| --- | --- |
| Gmail ingestion | Not built (deliberately deferred) |
| Google Classroom ingestion | Not built (deliberately deferred) |
| File upload ingestion | Built |
| Classification engine (Obligation/Study/Noise) | Built, verified live |
| Action Queue dashboard | Built, verified live |
| Study Plan engine | Built, verified live |
| **Assignment Scaffolding Assistant** | **Not built at all — no work done on this yet** |
| Human approval step | Built, verified live |
| Single-user demo auth | Not built |

Stretch goals (Classroom, reminders, attachment archiving, WhatsApp,
form/poll drafting, hosting) — none built, all still open by original
design (WhatsApp and hosting were always lowest-priority/optional).

**Rough completion estimate against the full documented plan: ~45–55%.**
Core reasoning/workflow engine is real and solid; the biggest gap is that
Assignment Scaffolding was on the Must-Have list and has not been started,
and the Stream/dashboard-density and Approval Drawer (slide-in panel) parts
of the design spec were never fully realized as originally written.

**Decision, stated explicitly by the user:** target full completion of the
documented Production Plan, not a reduced scope — including previously
stretch-tier items, time permitting.

---

## Jul 18 (continued) — Layout Pivots, Assignment Scaffolding, Auth, Approval Drawer

**Layout iterated twice more, same day, based on direct feedback:**
- Day 7c: consolidated the four-section Pulse Rail into a single
  continuous scrollable page, rail repurposed as a scroll-to-anchor jump
  menu instead of a section switcher.
- Day 7d: pivoted again, to a horizontal scroll-snap layout with four
  glass panels (semi-transparent, blurred, blunt corners), at the user's
  request, moving away from vertical scroll.
- Day 7d-fix: mouse-wheel scrolling didn't work on the glass panels
  (wheel input is vertical by default; the horizontal container never
  had it redirected) — fixed with a wheel-to-horizontal-scroll listener.
  The user made a further **manual, uncommitted fix** to scroll
  responsiveness themselves on top of this (commit `5186f2a`), which
  Codex later confirmed and preserved rather than overwriting.

**Day 8a — Assignment Scaffolding Assistant, built.** New
`backend/assignment_helper.py`, `scaffold_assignment()` reusing the
existing GPT-5.6 Luna client setup, structured JSON output
(requirements/concepts/approach/test_cases), explicitly constrained to
never produce a complete solution even if asked. New `assignment_help`
table, `POST /assignment/help`, `GET /assignment/history`. Fifth amber
glass panel added to the frontend. Committed as `4d2090e`.

**OpenCode diagnostic pass on Day 8a — mostly accurate**, with three
flagged items, all cross-checked against the actual code and correctly
found to be non-issues by Codex:
- "Queue grouping bug" (a yearless deadline landing in "Later" instead
  of "Immediate") — correct behavior, not a bug: the date genuinely
  resolves to its next future occurrence.
- Wheel-scroll conflict — not real; correctly deferring to the user's
  own manual scroll fix rather than fighting it.
- 5,000-char prompt limit — an intentional, defensible constraint, not
  a defect.

**Day 8b — single-user demo authentication, built.** Deliberately
minimal by design: `POST /auth/login` checks a shared `DEMO_PASSWORD`
against a random in-memory token (`secrets.token_hex`), all existing
routes except `/health` and `/auth/login` require a Bearer token,
frontend stores the token in `localStorage` and returns to a login
screen on any 401. Verified live by the user — both correct and
incorrect passwords behave as expected. Committed as `684ada9`.

**OpenCode hallucinated a materially different implementation of Day 8b
— worth recording plainly, since it's the second incident of its kind.**
Its report claimed: a new `backend/auth.py` module, **JWT tokens with
bcrypt**, and commit hash `6f4b2a1`. None of this matches what Codex
actually built — no `auth.py` exists, there is no JWT or bcrypt anywhere
in the codebase, and the real commit hash is `684ada9`. This reads as a
plausible-sounding fabrication rather than an actual reading of the
repository, not a small discrepancy. Caught before being acted on, since
the user had already manually verified login worked correctly. Same
lesson as the mid-Day-4 incident: OpenCode's own summaries are not
reliable enough to act on without independent verification, even when
everything else about the interaction seems normal.

**Day 8c — Approval Drawer, built per the original design spec.**
Replaced the flat Human Review panel with: a right-side slide-in drawer
(not a modal), semi-transparent ink scrim behind it, 3px amber left
border, ~250ms slide transition, full focus trap while open, focus
restored to the trigger on close, Escape-to-close, a persistent
pending-count badge on the fifth rail node that also opens the drawer
manually. Auto-opens when a new "Mark done" action is created, with that
action sorted to the top. Approve/Reject unchanged on the backend side —
this was a frontend-only presentation change, confirmed by an empty
`git diff` on `backend/`. Committed as `f7db11d`.

**OpenCode diagnostic pass on Day 8c — this time thorough and accurate**,
checking implementation against the spec point by point with actual file
and line references, not a generic summary. Found one genuine (cosmetic)
issue — dead CSS (`.pending-section` referenced in a shared selector
after the panel it styled no longer existed) — and correctly flagged
several other candidate issues as non-problems with specific reasoning,
rather than padding the report. Codex confirmed the one real finding and
fixed it in a small follow-up: `Day 8c-fix: Remove obsolete pending panel
style`, commit `65749cb`.

**Credit usage through this stretch** (2,500-credit pool, monthly plan
limit now sitting at 0% — all usage is coming from this pool): 2,500 →
2,480 (Day 7d-fix) → 2,461 (Day 8a) → 2,445 (Day 8b) → 2,423 (Day 8c +
cleanup fix). Roughly 15-30 credits per focused task; steady, not
alarming, but worth continuing to track the same way the monthly
percentage was tracked earlier in the week.

---

## Jul 19 — Ribbon Fix, Travel Animation, Archiving, Strategic Recalibration

**Human Review discoverability fix, user-requested.** The rail's
hover-only label for Human Review wasn't genuinely discoverable. Replaced
with a top-right amber ribbon (pending count + arrow, becomes an × close
control when the drawer is open). Committed as `f107217 Day 8c-fix: Human
Review approval ribbon`.

**Monthly plan quota exhausted, then a reset used deliberately.** Plan
limit hit 0% (no natural refill before the July 21 deadline, since the
cycle resets Aug 17). The one available free monthly reset was used
intentionally to convert dead/expired quota back into usable quota,
extending how long the 2,000+ credit pool lasts. Reset confirmed genuine
by the plan's reset date advancing from "Aug 17" to "Aug 18" in the
dashboard after use — not a scam, it visibly worked, it was simply spent
down again the same day by heavier tasks.

**Day 8d — classification-travel animation, built.** A colored particle
visibly travels from the Ingest result toward the matching rail node
(red/green), with an arrival pulse, before the underlying view refreshes;
Noise fades in place with no travel. `prefers-reduced-motion` respected.
Verified live via the session's own in-app browser control (real login,
real Obligation and Study Material submissions, console-clean). Committed
as `db18f68`.

**OpenCode diagnostic pass — accurate, one legitimate (non-bug) finding.**
Flagged that Study Material classification doesn't call `loadStudyPlan()`
afterward, since the animation visually implies data arriving there.
Codex's counter-explanation was correct and verified: Study Plan and
classified `items` are separate datasets by design (Study Plan is only
generated from explicit question-bank/notes uploads via `/study/upload`),
so refreshing it after a single-message classification would just
re-fetch unchanged data. No fix needed; OpenCode agreed after reviewing
the reasoning.

**Day 8e — attachment archiving, built.** Original uploaded file bytes
now persist to `backend/archive/` (gitignored) for both `/ingest` and
`/study/upload`, with new `archived_path` columns (additive migrations,
existing data untouched), a traversal-protected `GET /archive/{filename}`
download endpoint, and "Download original" links in the frontend. This
was the most expensive single task of the build (8m41s, multiple
live-server start/stop cycles) because it surfaced and fixed a real
pre-existing bug along the way: `/ingest`'s multipart validation checked
against FastAPI's `UploadFile` class specifically, which rejected
Starlette's actual runtime upload object — corrected to match the pattern
already working in `/study/upload`. Verified with real fixture files,
byte-for-byte download match confirmed. Committed as `4758371`.

**OpenCode diagnostic pass — thorough and accurate**, including running
its own path-traversal and byte-match tests rather than only reading
code. Flagged two cosmetic, non-functional notes (404 vs. 400 on a
specific traversal path shape; hardcoded `text/plain` media type, correct
given only `.txt` is accepted today). Codex's response was accurate and
verified; OpenCode independently re-checked Codex's specific claims
(rather than just accepting them) and confirmed each one. No fix needed.

**Strategic recalibration, user-initiated.** The user pushed back
directly on Claude's sequencing and tone — specifically, proposing
Reminders (a stretch item) ahead of Gmail/Classroom ingestion (Must-Have
items that had been deferred since Day 1 and not meaningfully revisited).
Assessed as a fair correction: the deferral was right on Day 1 to protect
the core build, but by Day 8, with the core solid, continuing to treat
Gmail/Classroom as low-priority was inertia, not a reasoned call.
**Decision: Gmail and Google Classroom ingestion move ahead of Reminders
in priority.** WhatsApp remains flagged for its specific, documented
compliance conflict with the rules' third-party-authorization clause
(not a general risk-aversion call) — agreed approach going forward is to
build a clearly-labeled simulated WhatsApp data path instead of a live
unofficial bridge, preserving the demo value without the actual rules
risk.

---

## Jul 19–20 — Reminders, Simulated WhatsApp, Connected Sources, Deployment Prep, Final Smoke Test

**Day 8d (reminder banner) verified live**, not just described: a real
same-day Obligation classification correctly triggered the banner with
accurate count and nearest-deadline text; session-only dismissal and
reload-reappearance both confirmed in-browser. Committed as `09c552a`.
Credits: 2,423 → 2,384 (ribbon fix) → continued down through Days
8d–8j at roughly the same 15–45-credit-per-task rate seen earlier in
the week.

**New Codex session started for the Day 8g/8h Google work**, session
start cost 2,288 credits remaining (fresh-session repo inspection).

**Day 8g — Gmail ingestion via OAuth, built.** Reusable
`google_client.py` (token load/refresh), `gmail_sync.py`, `POST
/sources/gmail/sync`, `source_id`-based deduplication. First
`credentials.json` supplied was a Web OAuth client, not Desktop —
correctly detected and blocked by the setup script with a clear error
rather than a broken flow; user regenerated the correct Desktop client.
Real OAuth consent completed by the user. Committed as `de306cc`.

**Day 8h — Google Classroom ingestion, built**, reusing the Gmail OAuth
foundation. Course-context-qualified deduplication IDs (Classroom
coursework IDs are only unique within a course, verified against
official Google API docs, not assumed). Committed as `2969e64`.

**Real OAuth scope mismatch hit on the college account**, distinct from
the earlier Web-vs-Desktop client issue: Google granted a narrower scope
set than requested for the college account specifically (likely a
Workspace admin policy restricting third-party API scopes for student
accounts) — `oauthlib`'s strict scope validation raised a Warning
exception on this. Fixed correctly by accepting and saving whatever
scope set Google actually grants, rather than hard-failing. Committed as
`8fff424`.

**Both Gmail and Classroom sync live-verified twice with real personal
data** — first pass: 15 Gmail messages, 31 Classroom items, 0 skipped
(correct for a first sync). Second pass (Day 8m smoke test): 6 new Gmail
messages processed, 9 correctly skipped as duplicates; Classroom
correctly skipped all 31 as already-seen. Real classifications inspected
directly from the database — genuine marketing/notification emails
correctly classified as Noise, real course materials correctly
classified as Study Material. This is the strongest evidence in the
whole build that the classification engine works on real, messy,
unstructured data, not just clean test fixtures.

**Day 8i — reminder banner, and Day 8j — simulated WhatsApp demo data,
both built** (Day 8i covered above out of strict order since it landed
mid-Gmail-work). Day 8j: hardcoded representative sample messages
(mandatory registrations, completion polls, casual noise), loaded via
`POST /sources/whatsapp/demo-load`, tagged `source="whatsapp-demo"` and
visually marked "Simulated" in the UI — deliberately not a live
unofficial-API bridge, per the standing compliance decision.

**Serious incident: `backend/triage.db` was deleted during Day 8j
verification.** While cleaning up an accidental scratch database created
by a misdirected test command, Codex removed the real, populated
`backend/triage.db` instead — all locally persisted items and study
plans at that point were lost (WhatsApp demo data had loaded
successfully just before this, but was lost with the database). Codex
stopped immediately, disclosed the mistake plainly, and asked permission
before doing anything further rather than attempting a silent fix. New
standing rule established as a direct result: database files are now
protected — no deletion or overwrite without a separate, explicit
approval — written into a new `AGENTS.md` file so it persists across
sessions, plus a manual `.bak` backup step before any future
database-adjacent cleanup. Database was recreated, Gmail/Classroom
resynced, WhatsApp demo data reloaded — full recovery, no lasting data
loss beyond that one session's manually-entered test items. Worth
recording plainly: this is a real mistake with real cost, but the
disclose-immediately, ask-before-proceeding response to it is exactly
the correct failure mode, and is genuinely worth including in the
README's Codex-collaboration section rather than omitted.

**Day 8k — Connected Sources panel, built.** Unified toggle UI
replacing three separate sync buttons — Gmail, Classroom, WhatsApp Demo
as working toggles; Slack and Teams present but inert/"Coming soon",
`aria-disabled` for accessibility. 30-day reconnect-prompt logic for
Google sources. New `GET /sources/google/status` backend endpoint
(exposes only whether authorization exists, never token contents).

**Day 8l — deployment configuration, built** (not live deployment
itself, which requires manual third-party account steps by the user,
still pending as of this log). Railway config for the backend
(`railway.toml`, `$PORT`-aware start command, health check, configurable
`CORS_ORIGINS`), Vercel config for the frontend (`vercel.json`, a small
runtime `api/config.js` endpoint exposing only the public backend URL,
keeping secrets on Railway). README updated with exact manual setup
steps and an honest limitations note: hosted Google OAuth won't work
(token.json is local-only), SQLite/archive storage isn't durable on
Railway's ephemeral filesystem. Day 8k and 8l ended up in a single
combined commit (`dbf70a6`) rather than two — a commit-history
organization detail, not a functional issue; Codex correctly declined to
rewrite already-published history to split it without being explicitly
asked to.

**Two full audit rounds on Day 8k/8l — both cross-verified, no real
defects found.** OpenCode's claims about Railway's `RAILPACK` builder
and restart-policy syntax were independently checked by Codex against
current official Railway documentation (not just asserted) and
confirmed accurate.

**Day 8m — final live smoke test + README Codex-collaboration section,
built and run for real.** All 17 endpoints tested live against an actual
running `uvicorn` server (not `TestClient`) except Gmail/Classroom sync,
which were correctly held back pending a fresh explicit confirmation
(same real-Google-data caution as before) — user ran those two live
personally once confirmed, both passed. Every endpoint now has genuine
live-HTTP evidence behind it, not a mocked or inferred pass. Committed
as `7b894c9`.

**Credit anchors through this stretch** (2,500-credit pool; monthly plan
limit has stayed at 0% throughout, all usage from this pool): 2,384 →
2,288 (new session start) → 2,238 (Day 8k+8l) → 2,221 (audit round) →
2,186 (Day 8m). Roughly 200 credits spent across Days 8d through 8m —
consistent with the per-task rate observed all week, no anomalies.
---

## Jul 21–22 — Review-Only Form Drafting, Deployment Fixes, Landing Flow, and Demo Readiness

The project moved from deployment preparation to a deployed, demo-ready build. The Vercel frontend and Railway API were connected, authenticated demo access was verified, and the remaining work focused on improving review safety, navigation reliability, and the student-facing product flow.

### Day 8n — Form/poll response drafting (`807c863`)

Triage gained a deliberately review-only way to prepare responses for routine completion polls and simple forms.

- Extended the classifier contract with optional `is_poll_or_form`; it defaults to false and does not change the existing required classification fields.
- Stored the flag additively in SQLite, including a migration for existing local databases.
- When a matching obligation is marked done, the API adds a conservative `drafted_response` to the pending-action payload:
  - completion polls use an explicit response such as “Suggested reply: YES, completed”;
  - simple fields such as name, roll number, email, and phone use blank templates rather than invented facts.
- The Approval Drawer displays that draft in an editable textarea above Approve/Reject, with clear copy-and-send-yourself wording.
- Approving still only updates the local Triage item. The application has no WhatsApp or external-form submission capability.

### Gmail compatibility repair (`cb21247`)

A Gmail sync edge case exposed a classification-schema compatibility issue. The schema was corrected so Gmail imports can pass through the same classification workflow without breaking the existing response shape.

### Day 8o — panel navigation reliability (`e00a819`)

The horizontal glass-panel interface was audited around the Action Queue, where nested scrolling had made leaving the panel unreliable.

- Wheel input now stays with inner scrollable content until that content is genuinely at its top or bottom boundary.
- At a boundary, vertical wheel input can navigate to the previous or next panel.
- Keyboard and rail navigation remained intact, and a visible navigation fallback was added.
- The Action Queue was tested after scrolling its inner list to the bottom: wheel navigation, navigation controls, and keyboard navigation all reached the next panel.

### Day 8p — production landing and app controls (`76fa2ae`)

The product flow was expanded into a public, explanatory landing experience followed by demo sign-in and the student workspace.

- Added a production-style landing page that explains the intended Triage system while honestly routing visitors into the present demo.
- Added responsive landing navigation, product sections, and a safe visual fallback for the landing artwork.
- Added floating app controls for profile, appearance, and application preferences.
- Appearance can follow the system by default or be set to light or dark mode; reduced-motion preference is respected.
- The landing page communicates the roadmap without claiming that unbuilt integrations already submit or act on a student’s behalf.

### Command-desk and visual refinement (`029b55a`, `33ab2d2`, `ad53a9f`, `5e32cd5`, `58aeed4`, `3a8415b`, `ab09c87`)

The app workspace was iterated into a more compact “student command desk.”

- Corrected landing-page section navigation and image sizing.
- Reworked the main desk for denser, easier-to-scan content: connected sources can collapse, obligation cards open details on demand, and study rankings use compact cards.
- Refined horizontal navigation to show adjacent panes without letting the left rail consume that visual gap.
- Replaced oversized navigation affordances with a full-height, vertical pulse rail that gives each panel a clear position.
- Added and refined the Triage pulse-mark brand treatment near the product name, including a subtle redraw animation and removal of an unwanted icon frame.

### Current local demo preparation (uncommitted at the time of this update)

A repeatable local demo-data seeder and rendering fix were prepared for recording a believable walkthrough.

- The seeder is additive and idempotent; it creates representative obligations, study items, polls, and classified records without deleting or resetting the protected local database.
- A frontend text-rendering correction fixes empty-looking dynamic cards caused by the prior HTML escaping approach.
- These local working-tree changes are intentionally recorded here separately from the commit history until they are reviewed and committed.

### Current state and honest boundaries

The deployed demo now supports the intended flow: public landing page → demo login → local-first student desk. Gmail and Google Classroom integrations require a user’s local OAuth setup, while WhatsApp remains representative demo data. Triage classifies, prioritizes, drafts, and stages decisions; it does not submit forms, send WhatsApp messages, or perform other external actions for the student.

---

## Build Summary Table (updated through Jul 22)

Credit records before Jul 21 are retained from the original build log. The project’s current balance was reported as approximately **1,900 credits**. Entries labelled “estimated” are allocations of the approximately 286-credit difference from the last recorded balance (2,186) and are not presented as exact billing records.

| Date / phase | Work | Commit(s) | Credit use |
| --- | --- | --- | --- |
| Day 1 | Rules review, category, repo setup, and scope narrowing | Historical build log | From plan — mostly planning |
| Day 2 | Local-first core: classifier, FastAPI, and minimal frontend | Historical build log | From plan — session reached 3% quota |
| Days 3–4 | Action Queue persistence and Study Plan engine | Historical build log | From plan — moderate |
| Day 6 | Approval layer (request → pending → approve/reject) | Historical build log | From plan — moderate |
| Days 7a/7c/7d | Design system and horizontal glass-panel layout pivots | Historical build log | From plan — higher than necessary |
| Day 8a | Assignment Scaffolding Assistant | Historical build log | ~16–19 credits |
| Day 8b | Single-user demo authentication | Historical build log | ~22 credits |
| Day 8c–8d | Approval Drawer and classification-travel animation | Historical build log | From plan — small |
| Day 8e | Attachment archiving and upload-validation repair | Historical build log | ~44 credits |
| Days 8f–8m | Google integration, reminders, WhatsApp demo data, deployment prep, and final smoke test | See dated entries above | ~200 credits across Days 8d–8m (recorded estimate) |
| Jul 21 | Superdesign workflow reference material | `387c362` | Estimated ~10 credits |
| Jul 21 | Review-only form/poll drafting | `807c863` | Estimated ~22 credits |
| Jul 21 | Gmail classification-schema compatibility repair | `cb21247` | Estimated ~8 credits |
| Jul 21 | Panel-navigation reliability | `e00a819` | Estimated ~30 credits |
| Jul 21 | Landing flow, app controls, and product polish | `76fa2ae`, `029b55a`, `33ab2d2` | Estimated ~80 credits |
| Jul 21–22 | Command-desk layout, pulse rail, and brand refinements | `ad53a9f`, `5e32cd5`, `58aeed4`, `3a8415b`, `ab09c87` | Estimated ~80 credits |
| Jul 22 | Local demo-data preparation and documentation updates (working tree at this log update) | Not yet committed | Estimated ~56 credits |
| **Current reported balance** | **Credits remaining** | — | **~1,900** |
