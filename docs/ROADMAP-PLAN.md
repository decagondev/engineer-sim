# Roadmap implementation plan

How each item in `docs/ROADMAP.md` gets built, in the same shape as the rest of the
codebase: a pure decision or model in `sim/core/`, I/O behind a port in
`sim/core/ports/`, adapters in `sim/adapters/`, wiring in `sim/app/composition_root.py`
and `manager.py`, routes as closures in `sim/adapters/web/app.py`, and one dock app or
dashboard tab per feature. Status: plan, 2026-09-22. Nothing here is built.

## Rules every item follows

- **Single responsibility.** One new module per concern. A feature never grows an
  existing class's job; it adds a service that takes the existing ports.
- **Open for extension.** New behaviour arrives as new ports, new dataclass fields with
  defaults, new routes, new dock apps, and new scenario YAML keys with defaults. Existing
  routes keep their payload shape; new keys are additive so old pages keep working.
- **Substitutable adapters.** Every port gets three implementations (sqlite, Firestore,
  memory) and one parametrised test that runs the same assertions across all three, as
  `test_we02` does for session files. Firestore adapters denormalise anything the
  dashboards need onto the session document (`INDEX_FIELDS`), never a read per row.
- **Small interfaces.** Ports expose the two or three methods their one caller needs.
  A store that is read in one place and written in another gets separate reader and
  writer protocols only if a second consumer appears.
- **Depend on ports.** `sim/core/` keeps passing `test_smk02_core_stays_pure`. Anything
  that talks to Groq, GitHub, Firestore or the clock is an adapter or an injected callable.
- **Cache discipline.** Any new API write goes through the existing middleware hook
  (`_after_mutation`), so overviews recount. Any new listing is one stream and is covered
  by a read-count test against the fake Firestore (`tests/unit/test_overview_reads.py`).
- **Every item ships with**: unit tests for the pure part, a route test with the fake
  auth, a guide update (`docs/onboarding/<role>/`), and a `CLAUDE.md` line if it adds a
  port or a concept.

## Phase 1: close the loop on grading

### 1. Instructor review: score override and comments (M)

**Core.** `sim/core/grading/review.py`

```python
@dataclass(frozen=True)
class HumanReview:
    session_id: str
    scores: dict[str, float]      # criterion key -> 0..1, only keys the instructor touched
    comment: str
    reviewer: str
    ts: str

def merge(grade: Grade, review: HumanReview | None, rubric: Rubric) -> Grade
```

`merge` returns a new `Grade` whose per-criterion scores are the human values where
present, recomputes the weighted total with the rubric, and marks each score with
`source: "human" | "model"`. Pure; tested with synthetic grades.

**Port.** `sim/core/ports/reviews.py`: `ReviewStore` with `save(review)`, `get(session_id)`,
`delete_for_session(session_id)`. Kept separate from `GradeStore` so the model grade and
the human verdict have independent lifecycles (a regrade must not erase a review).

**Adapters.** `sqlite_reviews.py` (table `reviews`, one row per session),
`FirestoreReviewStore` at `sessions/{sid}/reviews/latest`, plus `review_total` and
`reviewed_ts` written onto the session document, `memory_reviews.py`. Registered in
`stores.py` and `manager.py`.

**Web.** `PUT /api/instructor/session/{sid}/review` (instructor owning the session, or
admin) validates keys against the scenario rubric and 0..1 bounds. `GET /api/session/{sid}/grade`
and the export return the merged grade with a `review` block. `_enrich_sessions` gains
`reviewed` and the state `reviewed` after `graded` (violet stays for graded; add a fifth
colour only after re-running the palette validator, otherwise render reviewed as graded
with a check mark).

**UI.** Replay Assessment panel: each criterion row gets a small number input beside
the model score and the evidence; a comment box; **Save review**. The challenger's chat
strip shows "Reviewed 78% by your instructor" ahead of the model grade.

**Tests.** `merge` math; store round trip on three stores; route permissions; export
contains the review; overview counts `reviewed`.

### 2. Calibration from the dashboard (M)

**Core.** Existing `sim/core/grading/calibration.py` stays the maths. Add
`sim/core/grading/fixtures.py` with `fixture_from_session(rows, review, rubric, build_record) -> dict`
extracted from `sim/app/save_fixture.py::build_fixture` (the app module becomes a thin
CLI over it). A session with a human review is a fixture.

**Port.** `sim/core/ports/calibration.py`: `CalibrationRunStore` with `save(run)`,
`latest()`. A run records when, how many fixtures, the report, and pass/fail.

**App.** `sim/app/calibration_runner.py`: `run(fixtures, rubric, grader) -> CalibrationRun`
in a background thread with progress written to the run store (`status: running|done|failed`,
`done`, `total`). Uses the real provider through the same `build_grader`; refuses to run with
`LLM_PROVIDER=fake` unless a test passes a grader in.

**Web.** `POST /api/admin/calibration/run` (starts; 409 if one is running),
`GET /api/admin/calibration` (latest run and progress), `POST /api/admin/calibration/apply`
(sets `grader_calibrated=True` only when the latest run passed). Admin Settings → Grading
card shows fixture count (sessions with reviews), the last run's per-criterion agreement
table drawn with `SimViz.hbars`, a **Run calibration** button with a progress bar, and
**Mark calibrated** enabled only on a pass.

**Tests.** `fixture_from_session` round trip against the saved-fixture schema in
`calibration/README.md`; runner with a scripted `FakeLLMClient`; the apply route refuses
after a failed run.

### 3. Evidence that links back (S)

**Core.** `sim/core/grading/evidence.py`: `locate(evidence: str, rows) -> int | None`,
best-effort match of a quoted evidence string to a transcript message id (exact substring
first, then longest common run over 24 characters). Pure, tested.

**Web.** The grade payload's `scores[].evidence` gains a sibling `evidence_ref` (message
id or null), computed at grade time and stored with the grade so replays do not recompute.

**UI.** `renderGrade` renders evidence as a link when `evidence_ref` exists; clicking
scrolls the timeline (`renderEv` sets `data-id`) and flashes the row. No layout change.

### 4. Cohort results (M)

**Core.** `sim/core/reporting/cohort.py`: `cohort_results(rows, rubric) -> CohortReport`
(per-criterion mean, median, quartiles; not-submitted list; per-member row with state,
model total, review total). Pure over the enriched session dicts already produced by
`_enrich_sessions` plus stored grade bodies.

**Web.** `GET /api/instructor/cohorts/{cid}/results?scenario=` builds from one sessions
listing (filtered by assignee membership) and one grades listing; add `GradeStore.list(session_ids)`
(sqlite `IN`, Firestore one `get_all` batch) rather than a get per session. Cached through
`_cached` with key `cohort:{cid}:{scenario}`; CSV export at `.../results.csv`.

**UI.** Instructor **Cohort** tab gains a **Results** view: criterion bars, a
distribution strip per criterion, and the member table with links to replays.

## Phase 2: the interview experience

### 5. Visible timebox (S)

**Core.** `Scenario` gains `timebox_minutes: int = 0` (YAML key, default 0 = none);
`session_service.start` records `[timebox:20]` as a signal so the transcript carries it and
the replay can show it. The interview generator writes `timebox_minutes: 20`.

**Web/UI.** Scenario payload includes `timebox_minutes` and the session's `started_at`
(first event ts). `shell.js` shows a menubar countdown from `started_at`; past zero it
turns to "over by 3:12" in the signal colour. The assessor's context gets one line
("The candidate submitted 4 minutes over the timebox") built in `_assessor_context`
from the transcript, so the persona can mention it without the grader being told
to penalise.

### 6. Editor polish (S each, one commit each)

All in `static/apps/files.js` and `static/editor.js`; no backend.

- Find/replace: bind the vendored search addon (`Ctrl/Cmd+F`, `Ctrl/Cmd+H`).
- Resizable split: a drag handle between editor and preview, width remembered in
  `localStorage` per browser.
- Status bar word count for markdown tabs.
- Markdown shortcuts: `Ctrl/Cmd+B` / `I` wrap the selection; `Ctrl/Cmd+K` inserts a link.
- **Insert diagram** button on markdown tabs drops a starter ```mermaid block at the cursor.

### 7. Diff against the starter (M)

**Port.** `WorkspaceFiles` gains an optional `diff(root) -> str` (unified diff against the
baseline). `LocalWorkspaceReader` implements it with `git diff <first-commit>` (the code in
`GitBuildObserver.summary` moves into a shared `git_diff(workdir)` helper used by both);
`GitHubWorkspaceFiles` implements it with the compare API when the repo is a fork, else
returns "" with a note.

**Web.** `GET /api/session/{sid}/files/diff`. **UI.** A **What changed** tab in Files that
renders the diff read-only with `SimMD.highlight(text, "diff")`, per-file collapsible.

### 8. Assessor follow-through (S)

**Core.** `sim/core/session/interview.py`: `assessment_stats(rows, assessor_key) -> AssessmentStats`
(probes asked, answered, unanswered, mean answer length). `SessionService` exposes it;
`_enrich_build_record` appends "ASSESSMENT: answered 4 of 5 probes" so the grader cites
it under communication. The interview guide explains it.

## Phase 3: hosted build scenarios without leaving the browser

### 9. GitHub OAuth so Files can write to a linked repo (L)

**Port.** `sim/core/ports/oauth.py`: `OAuthBroker` with `start(uid) -> DeviceCode`,
`poll(uid, device_code) -> Token | None`. The existing `UserRecord.github_token_enc` stores
the resulting token (same Fernet box), so the resolver in `github_api.user_token_resolver`
needs no change.

**Adapters.** `sim/adapters/auth/github_oauth.py` implements the device flow against
GitHub with `GITHUB_OAUTH_CLIENT_ID`; a fake broker for tests. `GitHubWorkspaceFiles.write_file`
becomes real: read the blob sha from the cached tree, `PUT /repos/{o}/{r}/contents/{path}`
with a commit message "edit from workstation", update the cache's sha and blob. Refuses
when the resolved token is the classroom token (never commit as the operator).

**Web.** `POST /api/me/github/connect` (starts device flow, returns the user code and
URL), `GET /api/me/github/connect` (polls), `DELETE` (disconnects). `Workflow.editable`
for `repo` becomes true when the user has a token with `repo` scope; the scenario payload
already carries `editable`, so the Files app switches to writable with no change beyond
showing "commits to your fork".

**Tests.** Fake broker end to end; write through the fake GitHub JSON fixture (extend
`tests/regression/test_repo_workspace.py::FakeGitHub` with a `PUT` handler and sha bump);
refusal on the classroom token.

### 10. Live instructor view (M)

**Core.** Nothing new: the transcript is the event source.

**Web.** `sim/adapters/web/live.py`: a `SessionBus` (per-session set of subscriber
queues) that `post_tester_message` results and director events are published to from the
existing `/ws/{sid}` loop and the submit routes (one `publish(sid, rows)` call each).
`/ws/watch/{sid}` (instructor or admin, read-only) replays the transcript then streams new
rows. Single replica is already pinned, so an in-process bus is correct here.

**UI.** The replay gets a **Live** chip: when on, new events append to the timeline and
the Design panel refreshes on submission; the Overview's needs-attention list refreshes
from the bus too. Polling stays as the fallback when the socket drops.

## Phase 4: operations and performance

### 11. Query by owner and assignee in Firestore (S)

`FirestoreSessionRegistry.list_by_owner/assignee` use `where(field, "==", uid)` (the fake
already supports `where`). Composite indexes are not needed for a single equality filter.
The read-count test asserts an instructor's listing streams only their sessions.

### 12. Challenger dashboard (S)

`/api/me/sessions` already resolves titles from the registry with no per-session reads
(verified). Remaining work is presentational: include `state`, `grade_total` and
`reviewed` from the session index so a challenger sees "graded 78%" on their own list.

### 13. Session retention and archive (M)

**Port.** `sim/core/ports/archive.py`: `ArchiveStore.put(session_id, markdown) -> url`,
`list()`. Adapter: Firestore document with the markdown (under 1 MB; refuse larger) or,
when the artifact asset store is available, a file. **Web.** `POST /api/admin/sessions/archive`
with `older_than_days` and `states` (default `graded,reviewed`): export each session's audit
markdown, store it, cascade-delete, and report counts. Runs in a background thread with
progress like calibration. **UI.** Admin Sessions tab: an **Archive…** dialog with a dry-run
count first.

### 14. Audit log (M)

**Port.** `sim/core/ports/audit.py`: `AuditLog.append(entry)`, `list(limit, before)`.
Entry: ts, actor uid/email, action, target, summary. Adapters: sqlite table, Firestore
`meta/audit/entries` (append-only), memory. **Web.** A decorator-free approach that
matches the codebase: the admin mutation routes call `_audit(action, target, summary)`
explicitly; the middleware does not guess. `GET /api/admin/audit`. **UI.** An **Audit**
tab under `/admin` with a filter by actor and action.

### 15. Health that fails loudly (S)

`/health` gains `checks`: `store` (one cheap read with a 3 s timeout), `model`
(`GET /models` on Groq or the provider's equivalent, 5 s, only when a key is set),
`keys` (booleans). Returns 503 when the store check fails; the model check only warns,
so a Groq outage does not take the site down. Railway's `healthcheckPath` keeps pointing
at `/health`. Cached for 30 s so the health checker itself does not hammer Firestore.

## Later

- **Scenario authoring UI (L).** An admin editor over `scenario.yaml` fields with the
  reveal ladder as rows; writes go through a new `ScenarioStore` port so Firestore-hosted
  scenarios can override the on-disk ones (registry merges disk + store). The interview
  generator becomes a template picker.
- **Persona voice (S).** Browser `SpeechSynthesis` for the interviewer's brief and the
  assessor's questions; a mute toggle in Team Chat; no server change.
- **Mobile workstation (M).** Dock and Files at phone width for reading and chat; the
  editor stays desktop.
- **Model failover (S).** `ScopedLLMClient` gets an ordered fallback list from
  `LLM_FALLBACK_PROVIDERS`; a rate-limit error on the primary tries the next once and
  logs it; the admin deployment panel shows the last failover time.

## Sequencing

| Order | Items | Why this order |
|---|---|---|
| 1 | 1, 3, 2 | Reviews give calibration its data; evidence links make reviewing fast; calibration removes the caveat. |
| 2 | 11, 15, 12 | Small, protect the hosted server before the next cohort. |
| 3 | 5, 8, 6 | Interview feel, all small, visible to challengers immediately. |
| 4 | 4, 7 | Instructor and challenger insight; both reuse phase-1 data. |
| 5 | 10, 14, 13 | Operations once the class is running. |
| 6 | 9 | Largest; needs a GitHub OAuth app registered first. |

Each phase is one pull request per numbered item, tests green, docs and guides updated in
the same commit, following the commit-message style already in the log.
