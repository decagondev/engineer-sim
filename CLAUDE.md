# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Engineering Flight Simulator: a FastAPI app where a learner chats with LLM-driven personas
(client, stakeholders, interviewers), scopes real work in a sandbox, and gets graded by an LLM
against a rubric. Scenarios are YAML data. Runs locally on SQLite + a fake/local model; a hosted
variant (Railway + Firebase Auth + Firestore) is designed in `DEPLOYMENT-PLAN.md` and
`auth-plan.md`.

## Commands

```bash
pip install -r requirements.txt
python doctor.py                       # preflight: what's installed / missing

make run                               # LLM_PROVIDER=fake, uvicorn --reload on :8000
LLM_PROVIDER=ollama make run           # or groq (GROQ_API_KEY) / anthropic (ANTHROPIC_API_KEY)
python serve.py                        # bind 0.0.0.0 for a classroom LAN; prints URLs

pytest                                 # gating suite (smoke + regression + unit); evals deselected
pytest tests/smoke                     # fast deterministic suite
pytest tests/regression/test_mail.py   # one file
pytest tests/smoke/test_smoke.py::test_smk02_core_stays_pure   # one test
LLM_PROVIDER=ollama pytest -m eval tests/evals                 # real-model evals, non-gating, cost money
```

`pyproject.toml` sets `pythonpath = ["."]` and `addopts = "-q -m 'not eval'"`. Markers `firebase`
and `firestore` gate live tests behind `FIREBASE_TEST=1` / `FIRESTORE_TEST=1`; all normal tests run
on fakes (`FakeLLMClient`, `AUTH_MODE=fake`, `tests/unit/fake_firestore.py`). No conftest.

Python 3.11+ is required. On Windows, three tests fail for platform reasons only (CRLF in
`test_files02_read_text`, read-only `.git` objects blocking rmtree in `test_env02_teardown` and
`test_dock03_teardown`); do not treat those as regressions. Git also reports every LF file as
modified on Windows because of CRLF normalisation; check `git diff --numstat` before assuming
there are real changes.

Other tools:
- `python -m sim.app.calibrate --consistency` (real provider) grades the fixtures in
  `calibration/` against their human scores; `python -m sim.app.save_fixture <session-id> --score ...`
  banks a new fixture.
- `python tools/write_interview_scenarios.py` regenerates every `sim/scenarios/iv_*` folder from
  the `SCENARIOS` table inside the script. Edit the script, not the generated YAML.
- `python tools/email_templates.py show|apply` reads/updates the Firebase Auth email templates.
- `tools/migrate_sqlite_to_firestore.py`: one-shot copy of `sim.db` into Firestore.

## Architecture (ports & adapters)

**`sim/core/` is pure domain and must stay that way.** `test_smk02_core_stays_pure` AST-scans
every file under `sim/core/` and fails on imports of fastapi, starlette, uvicorn, sqlite3,
subprocess, anthropic, yaml, urllib, firebase_admin, httpx, google, cryptography, or anything
under `sim.adapters`. Put I/O behind a port in `sim/core/ports/` and implement it in
`sim/adapters/`.

**Wiring happens in exactly two places:**
- `sim/app/composition_root.py`: `build_llm`, `build_stores` (via `adapters/persistence/stores.py`),
  `build_environment`, `build_auth`, `build_director`, `build_registry`, `build_app`. Adapter
  selection is purely by env var through `sim/app/config.py` (`Config.from_env`).
- `sim/app/manager.py` (`SessionManager`): builds the shared stores once, then a per-scenario
  `Bundle` (SessionService + MailService + TicketService + Environment) cached by scenario key.
  A session resolves to a scenario through the settings store, so different sessions run
  different scenarios in one process.

**Config swaps, all env vars (see `Config`):**
- `LLM_PROVIDER` = fake | ollama | groq | anthropic. Groq uses httpx directly, no SDK.
- `PERSISTENCE` = sqlite (`SIM_DB_PATH`, default `sim.db`) | firestore (`FIREBASE_PROJECT_ID` +
  service-account file via `FIREBASE_CREDENTIALS_JSON` or `GOOGLE_APPLICATION_CREDENTIALS`).
- `AUTH_MODE` = password (`INSTRUCTOR_PASSWORD`, header `X-Instructor-Token`) | firebase | fake.
  Firebase verification is Identity Toolkit REST with the web API key; the service account is
  only needed for admin user mutations and Firestore.
- `ENV_PROVIDER` = local_folder | docker (per-session sandbox seeded from the scenario's
  `starter/` dir under `SANDBOX_ROOT`, default `.sandboxes/`).
- `BYOK_SECRET`: Fernet key for per-user secrets. `adapters/llm/scoped_client.py` wraps any
  LLM client so calls resolve the current user's Groq key (set via `request_context.py`)
  before falling back to the server key; `adapters/build/github_api.py::user_token_resolver`
  does the same for GitHub tokens (`UserRecord.github_token_enc`, edited in `/challenger`
  Settings) so repo browsing spreads rate limits across the class.
- `SIM_SCENARIO` points the registry at a single scenario file instead of auto-discovery;
  `GITHUB_TOKEN` raises the GitHub API rate limit for repo submissions and browsing;
  `PUBLIC_BASE_URL` pins the `/login` link in set-password emails (otherwise derived from
  each request's Host).
- `WORK_MODE` = auto | local | hosted. `Config.hosted` (auto: true when `AUTH_MODE=firebase`
  or `PERSISTENCE=firestore`) picks the workflow for product scenarios (see below).

**Per-turn flow:** WebSocket `/ws/{session_id}` in `sim/adapters/web/app.py` →
`SessionService.post_tester_message` → `PersonaResponder` (prompt built only from unlocked
reveal-ladder rungs, so the model cannot leak what it was never given) → `UnlockEvaluator`
(judge LLM decides if a rung unlocks) → `Director` runs triggers (`turn_count`, `submission`,
`session_start`, each gated by `min_level`) which emit chat messages, emails, or tickets.

**The transcript is the state machine.** `Director` and `SessionService` derive what has
happened by scanning stored messages with `kind == "event"` for marker strings such as
`[fired:<event_id>]`, `[ready:design]`, `[reveal] Submitted work:` and `[reveal] Submitted repo:`.
Anything that changes those strings changes trigger behaviour; grep for the marker before
editing it.

**Scenario tracks** (`track:` in scenario.yaml, default `product`):
- `product`: client + stakeholders, build in the sandbox, submit a patch or repo URL.
- `systems` (`sys_*`): doc-first design engagements; learners submit `DESIGN.md`.
- `interview` (`iv_*`, generated): a timed design interview. Personas carry a `lane`
  (`interviewer` or `assessor`). The assessor is hidden until a design exists: submitting
  `DESIGN.md` opens the assessment DM via `SessionService.maybe_begin_assessment`; saying
  "done" first (cue phrases in `sim/core/session/interview.py`) only nudges the learner to
  submit. Grading for this track
  uses `interview_posture`/`interview_expectation` in `sim/core/levels.py`, and
  `sim/core/design/diagram.py` renders the submitted doc as a mermaid diagram (served at
  `/api/session/{id}/diagram`), passed through `repair_mermaid` because models write labels
  mermaid cannot parse. The browser draws it with the vendored mermaid (`static/diagram.js`).

**Workflows** (`sim/core/workflow.py`, pure: `resolve_workflow(track, hosted)`): interview and
systems tracks are always `doc`; product is `sandbox` locally and `repo` when hosted. The web
layer exposes it as `workflow` on the scenario payload and every route switches on it:
- `doc`: the sandbox folder is auto-provisioned on first file access; the learner edits in the
  Files app; `POST .../submit-doc` reads `DESIGN.md` (+ `TICKETS.md`) from the workspace.
- `sandbox`: today's dev box; `POST .../submit-workspace` commits the working tree and records
  a `workspace` submission. Patch paste (`/submit`) and `starter.zip` are the offline fallback.
- `repo`: `POST .../workspace/repo` links a public GitHub URL (stored in session settings);
  Files browses it read-only via `adapters/workspace/github_files.py`; `/submit` and
  `starter.zip` are refused.

**Editable workspace:** `sim/core/workspace/service.py` (`WorkspaceService`) composes the
`WorkspaceFiles` port (local folder or GitHub, `ports/workspace.py`) with a `SessionFileStore`
overlay (`ports/session_files.py`; sqlite, Firestore, memory) holding only browser-edited
files, and replays them onto a re-provisioned folder (`hydrate`), so hosted redeploys lose
nothing. Writes go to the store first. `/files/write` and `/files/refresh` are the routes;
`static/editor.js` (`SimEditor`, vendored CodeMirror 5 under `static/vendor/`) is the editor.

**Instructor reviews** (`sim/core/grading/review.py`, `ports/reviews.py`): per-criterion
overrides plus a comment, stored apart from the model grade (`reviews` table /
`sessions/{sid}/reviews/latest`) and merged over it by `merge_review` whenever a grade is read
(`GET /grade`, export). The grade body stores the `weights` the total was computed with so the
merge recomputes totals faithfully. `PUT/DELETE /api/instructor/session/{sid}/review`; session
state `reviewed` follows `graded`.

**Grades are stored** (`ports/grades.py`; sqlite `grades`, Firestore `sessions/{sid}/grades/latest`,
memory): `POST /grade` saves the body with time and actor, `GET /grade` returns it, a regrade
replaces it, and the export uses it. Session rows get a `state` (`not_started` → `active` →
`submitted` → `graded`); a submission newer than the grade drops back to `submitted`.

**Dashboards** (`/api/instructor/overview`, `/api/admin/overview`, `/api/admin/sessions`) are
built from `_merge_known_sessions` + `_enrich_sessions` + `_session_stats` in the web app and
drawn by `static/viz.js`. On Firestore every per-session fact the dashboards need is
denormalised onto the session document (`INDEX_FIELDS` in `firestore_store.py`, written by the
submissions, grades, settings and registry stores; `index_session` backfills legacy docs), so a
listing is one stream. Payloads go through `_cached` (60 s stale-while-revalidate, warmed at
boot, `?fresh=1` from the Refresh buttons); any API write clears the sessions list and marks
the overviews for a background recount. Never add a read-per-row loop to these paths; a test
in `tests/unit/test_overview_reads.py` counts reads against the fake Firestore.

**Site settings** (`InstructorSettings`): default level, `allow_signup` (gates unknown
sign-ins in `AuthServices._sync_directory` and hides the button on `/login`),
`grader_calibrated` (None = env var) and `announcement`; edited on `/admin` → Settings.

**Submissions and build records:** every submit path ends in `remember_design` (design-doc
tracks) → `_maybe_diagram` → `after_submission` (director + assessor). `/grade` resolves the
build record per workflow in `_build_record_for`: GitHub commits + `DESIGN.md`/`README.md`
text (`adapters/build/github_observer.py`, REST, no clone), a sandbox git log
(`adapters/build/git_observer.py`), or a pasted patch. `SessionManager.lookup_design` makes
the design durable: latest submission → repo `DESIGN.md` → workdir file. Instructors set the
per-scenario starter repo URL via `/api/instructor/scenario/{key}/starter-url`
(`docs/PUBLISH-SCENARIOS.md`).

**Engineer levels** (`sim/core/levels.py`, intern → distinguished, default senior) scale which
triggers fire, persona posture, and rubric weighting.

**Roles and access:** three roles, admin > instructor > challenger. `sim/core/access/policy.py`
is pure authorization (Principal + SessionRecord → allow): admins see everything, instructors
only sessions they own, challengers only sessions assigned to them. Route guards in the web
layer call these predicates; in `AUTH_MODE=password` the instructor token stands in for an
instructor principal. `AUTH_BOOTSTRAP_ADMIN_EMAIL` promotes the first admin at boot. Cohorts
(`ports/cohorts.py`) group challengers so instructors can mint a session per member and admins
can bulk-onboard from pasted text.

**Scenarios** live in `sim/scenarios/<key>/scenario.yaml` + `starter/` and are auto-discovered
by `build_registry`. Adding one needs no code. The inline `_DEMO_SCENARIO` in composition_root
is a fallback and the canonical example of the schema.

**Web layer:** `sim/adapters/web/app.py` is one large `create_web_app` factory (all routes are
closures). Static desktop shell in `static/`: `shell.js` is the app registry; each dock app is
`static/apps/<id>.js` calling `SimApps.register(...)` plus one `<script>` tag in `index.html`
(see `docs/APPS.md`). Pages: `/` (learner), `/instructor`, `/login`, `/challenger`, `/admin`.

## Where the plans live

- `PLANNING.md`: epic/feature/story breakdown of the local MVP (waves 0–5b).
- `auth-plan.md`: identity design, role model, admin CRUD inventory, Firebase console steps.
- `DEPLOYMENT-PLAN.md` + `docs/HOSTING.md`: Railway + Firestore hosting, waves H0–H4, env
  var list, and the recorded decisions (no Postgres, one replica, BYOK Groq).
- `docs/ENVIRONMENT.md`: local_folder vs docker sandbox and the bind-mount model.
- `docs/WORKSPACE-PLAN.md`: design and delivery record for one workflow per track (doc /
  sandbox / repo), the in-browser editor, and repo-only submission when hosted.
- `docs/CLASSROOM.md`, `docs/INSTRUCTOR.md`, `GET_STARTED_*.md`: operator-facing run guides.
- `docs/onboarding/<role>/`: the in-app onboarding guides (served at `/onboarding`).
- `docs/ROADMAP.md`: what comes next, with sizes and the files each item touches;
  `docs/ROADMAP-PLAN.md`: the per-item design (ports, adapters, routes, tests, order).

## Things that bite

- Team Chat picks `wss://` from `location.protocol` in `static/apps/chat.js`; the Dockerfile
  passes `--proxy-headers` so uvicorn trusts Railway's TLS-terminating edge.
- WebSockets and the scenario bundle cache are in-process state: the app is single-replica
  (`railway.toml` pins `numReplicas = 1`).
- `FIREBASE_CREDENTIALS_JSON` may be a file path or the raw service-account JSON; both the
  Firestore client and the verifier's admin calls resolve it through
  `sim/adapters/auth/service_account.py`.
- Firestore stores derive sequence ids as read-max+1 and documents are capped at 1 MB.
- Firebase only honours custom email *bodies* once a sending domain is verified; until then
  `tools/email_templates.py apply` can change sender name and subject only.
- Firestore round trips from Railway are slow (hundreds of ms). Anything that loops over
  sessions or members must read from one listing, not one document per row; see Dashboards.
- Static files and `/onboarding` are served with `Cache-Control: no-cache`; `/health` reports
  the running commit and model, which is how to tell whether a deploy has landed.
- `sim.db`, `.sandboxes/`, and `*-firebase-adminsdk-*.json` are git-ignored; never commit them.
- Never add a third database. SQLite is local/test, Firestore is hosted (decision recorded in
  `DEPLOYMENT-PLAN.md`).
