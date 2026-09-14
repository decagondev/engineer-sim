# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Engineering Flight Simulator: a FastAPI app where a learner chats with LLM-driven personas
(client, stakeholders), scopes real work in a sandbox, and gets graded by an LLM against a
rubric. Scenarios are YAML data. Runs locally on SQLite + a fake/local model; a hosted variant
(Railway + Firebase Auth + Firestore) is designed in `DEPLOYMENT-PLAN.md` and `auth-plan.md`.

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
`test_files02_read_text`, read-only `.git` objects blocking rmtree in the two teardown tests);
do not treat those as regressions.

Grader calibration: `python -m sim.app.calibrate --consistency` with a real provider;
`python -m sim.app.save_fixture <session-id> --score ...` banks a fixture into `calibration/`.

## Architecture (ports & adapters)

**`sim/core/` is pure domain and must stay that way.** `test_smk02_core_stays_pure` AST-scans
every file under `sim/core/` and fails on imports of fastapi, starlette, uvicorn, sqlite3,
subprocess, anthropic, yaml, urllib, firebase_admin, httpx, google, cryptography, or anything
under `sim.adapters`. Put I/O behind a port in `sim/core/ports/` and implement it in
`sim/adapters/`.

**Wiring happens in exactly two places:**
- `sim/app/composition_root.py`: `build_llm`, `build_stores` (via `adapters/persistence/stores.py`),
  `build_environment`, `build_auth`, `build_director`, `build_app`. Adapter selection is purely
  by env var through `sim/app/config.py` (`Config.from_env`).
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
- `BYOK_SECRET`: Fernet key for per-user Groq keys. `adapters/llm/scoped_client.py` wraps any
  LLM client so calls resolve the current user's key (set via `request_context.py`) before
  falling back to the server key.

**Per-turn flow:** WebSocket `/ws/{session_id}` in `sim/adapters/web/app.py` →
`SessionService.post_tester_message` → `PersonaResponder` (prompt built only from unlocked
reveal-ladder rungs, so the model cannot leak what it was never given) → `UnlockEvaluator`
(judge LLM decides if a rung unlocks) → `Director` runs triggers (`turn_count`, `submission`,
`session_start`, each gated by `min_level`) which emit chat messages, emails, or tickets.

**Engineer levels** (`sim/core/levels.py`, intern → distinguished, default senior) scale which
triggers fire, persona posture, and rubric weighting.

**Roles and access:** three roles, admin > instructor > challenger. `sim/core/access/policy.py`
is pure authorization (Principal + SessionRecord → allow): admins see everything, instructors
only sessions they own, challengers only sessions assigned to them. Route guards in the web
layer call these predicates; in `AUTH_MODE=password` the instructor token stands in for an
instructor principal. `AUTH_BOOTSTRAP_ADMIN_EMAIL` promotes the first admin at boot.

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
- `tools/migrate_sqlite_to_firestore.py`: one-shot copy of `sim.db` into Firestore.

## Things that bite

- Team Chat picks `wss://` from `location.protocol` in `static/apps/chat.js`; the Dockerfile
  passes `--proxy-headers` so uvicorn trusts Railway's TLS-terminating edge.
- WebSockets and the scenario bundle cache are in-process state: the app is single-replica
  (`railway.toml` pins `numReplicas = 1`).
- `FIREBASE_CREDENTIALS_JSON` may be a file path or the raw service-account JSON; both the
  Firestore client and the verifier's admin calls resolve it through
  `sim/adapters/auth/service_account.py`.
- Firestore stores derive sequence ids as read-max+1 and documents are capped at 1 MB.
- `sim.db`, `.sandboxes/`, and `*-firebase-adminsdk-*.json` are git-ignored; never commit them.
- Never add a third database. SQLite is local/test, Firestore is hosted (decision recorded in
  `DEPLOYMENT-PLAN.md`).
