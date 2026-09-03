# Engineering Flight Simulator

A flight simulator for software engineers: talk to an AI client and stakeholders,
figure out what actually needs building, do the work in a real dev environment,
and get graded on how you did it.

## Start here

- **Learners:** read **[GET_STARTED_STUDENT.md](GET_STARTED_STUDENT.md)** — a
  from-nothing, 15-minute setup for macOS / Windows / Linux.
- **Instructors:** read **[GET_STARTED_INSTRUCTOR.md](GET_STARTED_INSTRUCTOR.md)**.
- **Coding tools & prerequisites (Cursor, Claude Code, Codex, OpenCode, git, Docker, Ollama):** **[docs/TOOLS.md](docs/TOOLS.md)**.

### One-command setup

```
./setup.sh                                   # macOS / Linux
powershell -ExecutionPolicy Bypass -File setup.ps1   # Windows
```

This installs everything and runs a **preflight check** (`python doctor.py`) that
tells you exactly what's installed, what's missing, and how to fix it — then
prints the start command tailored to your machine.

---

A local-first simulator where an engineer talks to AI personas, digs out what a
client *actually* needs (not what they asked for), handles an uninvited
stakeholder, and gets graded on how they ran the engagement. Runs on your laptop
for ~$0. See `PLANNING.md` for the full epic/feature/story/wave breakdown.

## Status — Waves 0–3 complete (MVP)

| Wave | What it added | State |
|---|---|---|
| 0 Walking skeleton | one persona, chat, SQLite, provider swap, pure core | ✅ |
| 1 Believable conversation | multi-persona, shared world, **reveal ladder** (anti-leak by construction) + real-model eval harness | ✅ |
| 2 Living scenario | **director** with turn-count triggers (the uninvited stakeholder), git build-record, scenarios-as-data | ✅ |
| 3 Assessment | weighted **rubric + LLM grader** with cited evidence, instructor grade endpoint | ✅ |
| 4 Hardening | grader calibration harness, second scenario (RAG), hosting-seams doc, character-consistency eval | ✅ |
| 5 Environment | per-session sandbox from a starter repo; build-for-real; grade auto-reads git build record | ✅ |
| 5b Docker env | **isolated per-session container** (bind-mount, mem/cpu/pid limits); same `Environment` port | ✅ |

**48 gating tests green; 3 real-model evals are non-gating (skipped unless a real
provider is set).** Build-for-real runs on Docker — see `docs/ENVIRONMENT.md`.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

make run                                   # free + deterministic (fake model)
LLM_PROVIDER=ollama make run               # free local model (needs ollama)
LLM_PROVIDER=anthropic ANTHROPIC_MODEL=<current> make run   # real quality
```

Open http://127.0.0.1:8000 — pick who to talk to (Priya / Marcus), ask
questions, and hit **Grade run**. With `fake`, personas reply with a canned line
(enough to see reveal events + the stakeholder fire); switch to ollama/anthropic
to actually converse.

## The interface

You log into a **workstation**: a desktop with a dock of apps. Click **Team
Chat** to talk to the client and stakeholders, **Workspace** to spin up your
sandbox, **Mail** for threaded email (a stakeholder may email you a scope change
mid-shift — it shows as a dock badge), **Files** to browse your sandbox, and
**Tickets** to scope the work on a board. Apps are modular — adding one is a
single file + a `register()` call, see `docs/APPS.md`. The shell never changes.

Inside Team Chat it's a multi-pane workroom, not a single thread:

- A **people** rail — you start talking to the client; other stakeholders
  appear in the rail when they show up (the uninvited VP *joins* mid-session,
  with an unread badge on his conversation).
- **Typing indicators** while a persona composes a reply, real timestamps,
  and the simulator's own signals (reveals, joins, session state) styled as a
  distinct class from human messages.
- **Reload-safe:** the session id lives in the URL; refreshing replays the
  whole conversation from the transcript instead of starting over.

## Test it

```bash
make test         # smoke + regression (deterministic, fast)
make smoke
make regression
LLM_PROVIDER=ollama pytest -m eval tests/evals   # real-model behavior (non-gating)
```

## How it hangs together (ports & adapters)

`sim/core/` is pure domain — no framework, no I/O (a smoke test fails the build
if that's ever violated). Everything swappable sits at the edge behind a port.
Wiring happens once in `sim/app/composition_root.py`.

```
core/
  persona/    persona + reveal ladder, responder, unlock evaluator
  world/      shared world state (single source of truth)
  director/   triggers (OCP) + events + director
  session/    the per-turn orchestration
  grading/    rubric + LLM grader (strategy)
  scenario/   scenario aggregate (personas + triggers + rubric as DATA)
  ports/      llm · repository · state · build_record
adapters/
  llm/        fake · ollama · anthropic
  persistence/ sqlite (transcript + unlock state) · in-memory
  build/      git observer (commits + net diff)
  web/        FastAPI + WebSocket + minimal UI
scenarios/    churn_dashboard/scenario.yaml
tests/        smoke/ · regression/ · evals/ (non-gating)
```

### Two seams worth understanding
- **`LLMClient` port** — makes the provider a config swap *and* lets every gating
  test run deterministically via `FakeLLMClient`.
- **Reveal ladder** — locked rungs are never placed in the persona's prompt, so
  the model *cannot* leak what it hasn't been given. Whether a real model holds
  the line is measured by the eval harness (EVAL-01), not the gating suite.

## Scenarios

The app hosts a library of scenarios (each `scenarios/<key>/scenario.yaml`,
tagged with a `difficulty`). Each session is assigned one — different trainees
can run different scenarios at once. Ships with a scenario for **every engineer level**: `intern_signup` (intern),
`junior_helpsearch` (junior), `churn_dashboard` (mid), `support_copilot` (senior),
`staff_pipeline` (staff), `principal_flags` (principal), and
`distinguished_mlplatform` (distinguished). Each has a real hidden need behind a
reveal ladder, level-appropriate stakeholder pressure, and a starter repo. Instructors
assign a scenario + level per session from the **instructor dashboard** at
`/instructor` (onboarding on first run, a new-session setup screen that hands you
a trainee link, sessions + replay, and settings).

## Engineer levels (adaptive difficulty)

Every session runs at an engineer level (`intern`…`distinguished`, default
`senior`). The level scales **pressure** (which stakeholders appear and how
early — an intern gets one gentle stakeholder, a staff engineer gets
overlapping ones), shapes **persona posture** (patient mentor → terse peer),
and shifts the **grading bar** to expectations (same criteria, level-weighted;
still `calibrated:false` until per-level calibration is run). Scenarios carry a
`difficulty` tag so a junior isn't handed a staff problem. Instructors set the
level via the gated endpoints (dashboard UI is the next wave).

## Instructor replay

Open **`/instructor`** and enter the instructor password (default
`$T0mV13w`, override with `INSTRUCTOR_PASSWORD`) to watch any recorded
session back — scrub or play the timeline across chat, mail, tickets, and
the reveal/stakeholder beats, and grade it. This is a **light gate, not real
auth** (shared secret, cleartext over HTTP) — fine for a trusted local
machine, not for untrusted users. See `docs/INSTRUCTOR.md`.

## Calibrating the grader (before you trust a score)

The grader works mechanically, but a working grader is not a *valid* one. Run the
calibration harness against a real model with real instructor-scored fixtures:

```bash
LLM_PROVIDER=anthropic ANTHROPIC_MODEL=<current> python -m sim.app.calibrate --consistency
```

It reports how well machine scores agree with humans (MAE, bias, within-tolerance,
rank correlation) and how stable the grader is on re-grades (self-consistency).
It exits non-zero until the thresholds pass. Only then set `GRADER_CALIBRATED=true`
— until you do, `/grade` returns `calibrated:false` and the UI shows a caveat.

### Banking a fixture after a playtest

Turn a finished session into a calibration fixture in one command (see
`docs/PLAYTEST.md` for the full protocol):

```bash
python -m sim.app.save_fixture <session-id> \
    --score discovery=0.75 --score scoping=0.4 \
    --score stakeholders=0.6 --score communication=0.7 \
    --summary "..." --repo /path/to/repo --grade
```

> The 5 seed fixtures in `calibration/` use **placeholder** human scores to
> exercise the harness. Replace them with real instructor scores (aim for >=10,
> spanning the quality range) before treating a PASS as decision-grade.

## Authoring a new scenario
Copy `sim/scenarios/churn_dashboard/scenario.yaml`, change the personas,
reveal ladders, triggers, and rubric, then point at it:

```bash
SIM_SCENARIO=path/to/scenario.yaml make run
```
No code changes needed — that's the Open/Closed payoff.

## Known limits (honest list)
- Single-process, single-user, no auth — by design for the MVP.
- Reveal-unlock and grading quality depend on the model; validate with evals +
  human calibration before trusting scores.
- Grader calibration HARNESS exists and is tested; the actual PASS still
  needs a real model run over real human-scored fixtures.
- Build record reads a local git repo the tester points at; no cloud env yet.
