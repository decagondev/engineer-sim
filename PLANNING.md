# Engineering Flight Simulator — MVP Plan

> A local-first simulator where an engineer clones a repo, talks to AI personas
> (client / manager / uninvited stakeholder), figures out what to actually build,
> ships it, and gets graded. This document is the design + delivery plan.

---

## 0. Scope of this MVP

**In scope**
- Runs entirely on a developer's local machine (no cloud, no auth, single user).
- Tester uses **their own** editor and coding agent; the "environment" is a **git repo they clone**.
- A local web app hosting: a fake-Slack chat surface, an instructor/control panel, and the persona/director backend.
- Personas with a public layer and a hidden layer (real need withheld behind a "reveal ladder").
- A director that fires timed + triggered events.
- One complete, graded scenario end-to-end.
- Transcript + git history as the recording. Rubric + LLM grader (calibrated against a human).

**Explicitly out of scope (deferred, noted where it plugs in later)**
- Real Slack/email integration, containerized "real computer", hosting, multi-tenancy, concurrent sessions, screen capture, billing.

**Cost target:** ~$0 during dev (personas run against a **local model via Ollama**); a few dollars of API per real graded session. The provider is a config swap, so quality passes / real sessions use the Anthropic API.

---

## 1. Architecture: Ports & Adapters (Hexagonal)

The **core** is pure domain logic with no framework and no I/O. Everything uncertain or
swappable (LLM provider, storage, web transport, git) sits at the edge as an **adapter**
behind a **port** (an interface the core owns). This is what makes the whole thing testable
and honest.

```
                 ┌─────────────────────────── adapters (edge) ───────────────────────────┐
   HTTP/WS  ──►  │  web (FastAPI)                                                          │
                 │        │                                                                │
                 │        ▼                                                                │
                 │   ┌────────────────────── core (pure domain) ──────────────────────┐   │
   Ollama/  ◄──► │   │  Persona · WorldState · Director · Scenario · Grader           │   │
   Anthropic     │   │        ▲ depends only on ports ▲                                │   │
   (LLM port)    │   └────────┼───────────────┼───────────────┼──────────────────────┘   │
                 │            │               │               │                            │
   SQLite   ◄──► │   Repository port   Recorder port   BuildRecord port  ◄── git observer  │
                 └────────────────────────────────────────────────────────────────────────┘
```

**Rule that keeps it clean:** `core/` may not import `adapters/`, FastAPI, the Anthropic SDK,
or SQLite. Dependencies point *inward*. All wiring happens once in the **composition root**.

### 1.1 Module / directory layout

```
sim/
  core/                       # pure domain — no framework, no I/O
    persona/
      persona.py              # Persona entity: public layer, hidden layer, reveal ladder
      responder.py            # produces an in-character reply (uses LLMClient port)
    world/
      world_state.py          # single source of truth for shared facts
    director/
      director.py             # decides who speaks; evaluates triggers; fires events
      triggers.py             # Trigger ABC + Timed/Event/State triggers
      events.py               # Event / Action value objects
    scenario/
      scenario.py             # Scenario aggregate (personas + world + triggers + rubric + repo)
      schema.py               # declarative schema + validation
    grading/
      rubric.py               # Rubric, Criterion, Score
      grader.py               # Grader strategy (uses LLMClient port)
    ports/                    # the abstractions the core owns
      llm.py                  # LLMClient
      recorder.py             # MessageWriter / MessageReader (segregated)
      repository.py           # SessionRepository, MessageRepository
      build_record.py         # BuildRecordSource
  adapters/
    llm/{ollama_client.py, anthropic_client.py, fake_client.py}
    persistence/sqlite_repo.py
    build/git_observer.py
    web/{app.py, ws.py, routes/}
  app/
    composition_root.py       # dependency wiring (the ONLY place adapters meet core)
    config.py                 # env/config; selects LLM provider, db path, scenario dir
  scenarios/                  # DATA, not code
    churn_dashboard/{scenario.yaml, personas/, rubric.yaml, starter_repo_ref}
  tests/
    smoke/                    # fast, run every change, uses FakeLLMClient
    regression/               # guards specific behaviors, uses FakeLLMClient
    evals/                    # slow, real-LLM, tolerance-based, NON-blocking
    fixtures/                 # canned transcripts, diffs, scenario stubs
```

### 1.2 SOLID mapping (concrete, not hand-wavy)

| Principle | How it shows up here |
|---|---|
| **S**ingle Responsibility | `Persona` = character behavior only (no transport/storage). `Director` = orchestration only. `Recorder` = logging only. `Grader` = assessment only. |
| **O**pen/Closed | New behaviors are added, not edited in: new **personas/scenarios** = data files; new **triggers** implement `Trigger`; new **grading strategies** implement `Grader`; new **LLM providers** implement `LLMClient`. The `Director` never changes to add an event type. |
| **L**iskov | Any `LLMClient` (`Ollama`, `Anthropic`, `Fake`) is substitutable — the core can't tell which is behind the port. Same for `Recorder` and `BuildRecordSource`. |
| **I**nterface Segregation | `Recorder` is split into `MessageWriter` and `MessageReader`, so the read-only `Grader` never depends on write methods. Scenario **authoring** interface is separate from scenario **runtime** interface. |
| **D**ependency Inversion | Core depends on `ports/` abstractions; adapters implement them; the **composition root** injects concretes at startup. No domain file imports a framework or SDK. |

---

## 2. Backlog hierarchy — definitions

- **Wave** — a delivery increment / milestone. Each wave is independently runnable and demoable, and has an **exit criterion**. Waves reconcile the epics into a build order.
- **Epic** — a major capability.
- **Feature** — a shippable chunk inside an epic.
- **User Story** — `As a <role> I want <goal> so that <reason>`, with acceptance criteria.
- **Slice** — a thin vertical task cutting top-to-bottom (UI→core→adapter) that delivers something demonstrable in a day-ish.

**Roles:** **Tester** (the engineer being simulated), **Instructor** (designs scenarios, reviews sessions), **Developer** (us, building platform capability).

---

## 3. Waves (delivery increments)

| Wave | Name | Goal | Exit criterion |
|---|---|---|---|
| **0** | Walking Skeleton | Prove the *feel*: one persona, minimal chat, end-to-end round trip locally. | You can message a persona in a browser and get a stateful, in-character reply that persists and survives a reload. Smoke suite green. |
| **1** | Believable Conversation | Multiple personas that don't contradict and don't leak the answer. | Two personas share world state; a "direct ask" for the hidden need is deflected; anti-leak regression tests pass. |
| **2** | Living Scenario | Director + events + scenario-as-data + recording. | A full scenario loads from a file, the uninvited stakeholder fires on trigger, and a complete transcript + git build-record exports. |
| **3** | Assessment | Rubric + LLM grader + instructor review, calibrated to a human. | One scenario is graded end-to-end on a real human; grader output cites evidence and lands within tolerance of your manual score across ≥10 fixtures. |
| **4** | Hardening & Handoff-ready | Second scenario, full regression suite, seams for future hosting. | Two scenarios interchangeable via config; regression + eval suites run in CI; containerization/hosting seams documented (not built). |

---

## 4. Epics → Features → Stories → Slices

### Epic A — Foundation & Architecture  *(Wave 0)*
Establish the hexagonal skeleton and the swap-the-LLM seam.

**Feature A1 — Composition root & config**
- **A1.1** *As a Developer, I want a single composition root wiring core to adapters, so dependencies point inward and nothing else knows about concretes.*
  - AC: core imports only `ports/`; a lint/import check fails the build if `core/` imports `adapters/` or a framework.
  - Slices: (a) `config.py` reads provider/db/scenario-dir; (b) `composition_root.build_app()` returns a wired app; (c) import-boundary test.
- **A1.2** *As a Developer, I want provider selection by config so I run free locally and paid for quality passes.*
  - AC: `LLM_PROVIDER=ollama|anthropic|fake` switches the concrete with no core change.

**Feature A2 — LLM port + adapters**
- **A2.1** *As a Developer, I want an `LLMClient` port with Ollama, Anthropic, and Fake implementations, so the core is provider-agnostic and testable.*
  - AC: all three satisfy the same `complete(messages, system) -> str` contract; a Liskov contract test runs against each.
  - Slices: (a) define `LLMClient`; (b) `FakeLLMClient` (canned/scriptable); (c) `OllamaClient`; (d) `AnthropicClient`.

**Feature A3 — Persistence port + SQLite**
- **A3.1** *As a Developer, I want `SessionRepository`/`MessageRepository` ports over one SQLite file, so storage is swappable and zero-infra.*
  - AC: messages persist and read back in order; DB is a single file; repo has an in-memory fake for tests.

---

### Epic B — Persona Engine  *(Waves 0–1)*
The heart of the product.

**Feature B1 — Persona model**
- **B1.1** *As an Instructor, I want a persona defined by a public layer (name/role/voice) and a hidden layer (real need, constraints), so the gap between stated and actual is authorable.*
  - AC: persona loads from data; public vs hidden fields are distinct; hidden fields never appear in a reply unless unlocked.

**Feature B2 — In-character responder**
- **B2.1** *As a Tester, I want a persona that replies in character and remembers the conversation, so it feels like a real person.*
  - AC: reply is non-empty, in voice, and references prior turns; runs against `FakeLLMClient` deterministically in tests.

**Feature B3 — Reveal ladder (anti-leak)**  *(Wave 1)*
- **B3.1** *As an Instructor, I want a "what to withhold / what unlocks it" ladder, so personas stay productively vague until asked the right question.*
  - AC: a direct "just tell me what you need" is deflected; a good discovery question unlocks the next rung; unlock state is tracked per session.
  - Slices: (a) ladder schema; (b) unlock evaluation; (c) deflection behavior; (d) leak regression fixtures.

---

### Epic C — Conversation Surface (fake Slack)  *(Waves 0–1)*

**Feature C1 — Chat transport**
- **C1.1** *As a Tester, I want a browser chat panel over WebSocket, so I can talk to personas live.*
  - AC: connect, send, receive; reconnect replays history from the repository.

**Feature C2 — Channels & DMs**  *(Wave 1)*
- **C2.1** *As a Tester, I want channels and direct messages with multiple personas, so conversations feel organized like real work.*
  - AC: a message routes to the right persona(s); personas can post to a shared channel.

---

### Epic D — Director & Events  *(Wave 2)*

**Feature D1 — Trigger abstraction**
- **D1.1** *As a Developer, I want a `Trigger` interface with Timed / Event / State implementations, so new triggers don't modify the Director (OCP).*
  - AC: adding a trigger type requires no edit to `director.py`.

**Feature D2 — Orchestration & the uninvited stakeholder**
- **D2.1** *As an Instructor, I want to script an event (e.g., a stakeholder appears at minute 20 or on first commit), so pressure is realistic.*
  - AC: the event fires exactly once when its trigger evaluates true; firing is recorded in the transcript.

---

### Epic E — Scenario System  *(Wave 2)*

**Feature E1 — Declarative scenario schema + loader**
- **E1.1** *As an Instructor, I want a scenario defined as data (personas + world state + triggers + rubric + starter-repo ref), so I change the client and keep the environment (OCP).*
  - AC: loader validates schema and fails loudly on a bad scenario; two scenarios are interchangeable via config.

**Feature E2 — Starter repo linkage**
- **E2.1** *As a Tester, I want a clone-able starter repo per scenario, so the "environment" is real code I build in.*
  - AC: scenario references a repo/template; instructions tell the tester to commit often.

---

### Epic F — Recording & Build Record  *(Wave 2)*

**Feature F1 — Transcript / event log**
- **F1.1** *As an Instructor, I want every message + event timestamped and append-only, so I can replay exactly what happened.*
  - AC: ordered, complete, exportable (JSON + human-readable).

**Feature F2 — Git build observer**
- **F2.1** *As an Instructor, I want the tester's commits and final diff captured as the build record, so I see how they built, not just the result.*
  - AC: `BuildRecordSource` returns commit timeline + final diff; optional timed auto-commit watcher.

---

### Epic G — Assessment & Grading  *(Wave 3)*

**Feature G1 — Rubric model**
- **G1.1** *As an Instructor, I want a definition-of-done + weighted rubric authored with the scenario, so grading is defined up front.*
  - AC: rubric = criteria with weights + descriptors; authoring is part of scenario data.

**Feature G2 — LLM grader with evidence**
- **G2.1** *As an Instructor, I want a grader that scores transcript + diff against the rubric and cites evidence, so scores are explainable.*
  - AC: output = per-criterion score + quoted/located evidence; deterministic against a fixed fixture with `FakeLLMClient`.

**Feature G3 — Human-in-the-loop calibration**  *(the honesty gate)*
- **G3.1** *As an Instructor, I want to compare grader output to my manual scores, so I only trust it once calibrated.*
  - AC: a calibration report shows grader-vs-human delta across ≥10 fixtures; grading strategy is swappable (`LLMGrader` / `HumanGrader` / `Hybrid`).

---

### Epic H — Instructor / Control Panel  *(Waves 2–3)*

**Feature H1 — Session lifecycle**
- **H1.1** *As an Instructor, I want to start / monitor / end a session for a chosen scenario, so I can run and observe a run.*
  - AC: start picks a scenario; live view streams messages/events; end triggers grading.

**Feature H2 — Review view**
- **H2.1** *As an Instructor, I want transcript + build record + score on one screen, so I can review a completed session.*

---

### Epic I — Quality & Test Harness  *(cross-cutting, all waves)*
See Sections 5–7 — this epic *is* the smoke/regression/eval suites plus the import-boundary and Liskov contract checks. Every other epic's stories are "done" only when their smoke/regression coverage is green.

---

## 5. The honesty problem: testing an LLM-driven system

You **cannot** unit-test LLM output deterministically. The architecture solves this with the
`LLMClient` port, giving three tiers:

1. **Smoke + Regression** run against **`FakeLLMClient`** (canned, scripted responses). Deterministic, free, fast, run on every change and in CI. These test *your* logic — routing, unlock state, event firing, persistence, grader plumbing — not the model.
2. **Eval harness** runs against a **real model**, asserts with **tolerances** (keyword/regex checks, or LLM-as-judge) over N runs with a pass threshold (e.g. "hidden need not leaked in ≥9/10 runs"). Slow, costs money, **non-blocking** (scheduled/nightly, not on every commit).
3. **Manual calibration** (Epic G3) — a human periodically checks grader validity. Nothing ships a grading decision to a real user until this passes.

This split is the whole reason the port abstraction earns its keep.

---

## 6. Smoke tests (fast, every change, `FakeLLMClient`)

Purpose: prove the system isn't fundamentally broken. Target < 30s total.

- **SMK-01 App boots** — composition root builds the app with `LLM_PROVIDER=fake`; health endpoint returns 200.
- **SMK-02 Import boundary** — static check: no `core/*` module imports `adapters`, FastAPI, SQLite, or an SDK.
- **SMK-03 WebSocket round trip** — connect, send a message, receive a reply.
- **SMK-04 Persistence round trip** — write a message, read it back, order preserved.
- **SMK-05 Persona replies** — persona returns a non-empty in-character reply (fake canned).
- **SMK-06 Scenario loads** — the sample scenario passes schema validation and instantiates.
- **SMK-07 Session lifecycle** — start → message → end runs without error and produces a transcript.
- **SMK-08 Grader plumbing** — grader called on a fixture transcript returns a score object with all rubric criteria present.

---

## 7. Regression tests (guard specific behaviors, `FakeLLMClient`)

Purpose: stop known-good behavior from silently breaking.

- **REG-01 Liskov / provider contract** — `Ollama`, `Anthropic`, `Fake` all satisfy the `LLMClient` contract test (shape, error handling, message mapping).
- **REG-02 Hidden layer never leaks unprompted** — with a scripted fake, a "just tell me what you need" turn does **not** surface any hidden-layer field; asserted on output.
- **REG-03 Reveal ladder unlocks correctly** — a scripted "good discovery question" advances unlock state by exactly one rung; a bad one does not.
- **REG-04 World-state consistency** — two personas asked the same shared fact (deadline/budget) return the same value.
- **REG-05 Director fires once** — a Timed/Event trigger fires its event exactly once and is logged; re-evaluation does not re-fire.
- **REG-06 Trigger OCP** — adding a new `Trigger` subclass requires no change to `director.py` (enforced by a test that registers a dummy trigger).
- **REG-07 Transcript integrity** — export is complete, ordered, and includes fired events with timestamps.
- **REG-08 Build record shape** — `BuildRecordSource` returns commit timeline + final diff for a fixture repo.
- **REG-09 Grader determinism + evidence** — on a fixed fixture with the fake, grader output is stable and every non-zero criterion cites locatable evidence.
- **REG-10 Interface segregation** — `Grader` depends only on `MessageReader` (a compile/type check that it never calls write methods).
- **REG-11 Scenario swap** — switching the configured scenario changes personas/rubric with no code change and both still pass SMK-06/07.

---

## 8. Eval harness (real-LLM, tolerance-based, non-blocking)

Not gating; scheduled. Each asserts a **pass rate over N runs**, not a single output.

- **EVAL-01 Anti-leak under adversarial asks** — across a bank of "tell me the answer" phrasings, hidden need stays withheld ≥ threshold.
- **EVAL-02 Productive vagueness** — persona's early replies are on-topic but under-specified (LLM-as-judge rubric).
- **EVAL-03 Character consistency** — voice/persona holds across a long session without contradiction.
- **EVAL-04 Grader validity** — grader score correlates with human score across the calibration fixture set within tolerance (feeds Epic G3).

---

## 9. Definition of Done (applies to every story)

1. Code sits on the correct side of the port boundary (core stays pure).
2. Smoke suite green; relevant regression tests added and green.
3. New swappable behavior added via an interface, not by editing a core class (OCP check where applicable).
4. Public behavior demoable locally with `LLM_PROVIDER=fake`.
5. If it touches persona/grader *behavior*, an eval case exists (may be non-blocking).

---

## 10. Start here (Wave 0 slice order)

1. A1.1 composition root + import-boundary test (SMK-02).
2. A2.1 `LLMClient` + `FakeLLMClient` (unblocks all deterministic tests).
3. A3.1 SQLite `MessageRepository` + in-memory fake (SMK-04).
4. C1.1 WebSocket chat panel (SMK-03).
5. B1.1 + B2.1 one persona, public/hidden model, in-character reply (SMK-05).
6. Wire H1.1 minimal start/message/end; export transcript (SMK-07).

Hit those and Wave 0 exit is met: you can talk to a stateful, in-character persona in a
browser, it persists, and the smoke suite is green — on your laptop, for ~$0.

---

## 11. Build status (appended after implementation)

Waves 0–3 are implemented, wired, and green. This section records what actually
shipped so the plan and the code don't drift.

**Delivered**
- Wave 0 — pure hexagonal core, `LLMClient` port (fake/ollama/anthropic), SQLite
  transcript, WebSocket chat, composition root, import-boundary test.
- Wave 1 — multi-persona cast with per-persona DM channels; shared `WorldState`;
  **reveal ladder** with an `UnlockEvaluator` (anti-leak by construction: locked
  rungs never enter the prompt); non-gating real-model eval harness.
- Wave 2 — `Director` with a `Trigger` OCP seam (`TurnCountTrigger`) and `Event`s;
  the uninvited-stakeholder appearance; `GitBuildObserver` build record;
  scenarios (personas + triggers + rubric) fully expressed as YAML data.
- Wave 3 — weighted `Rubric` + `LLMGrader` strategy returning per-criterion
  scores with cited evidence; `/grade` endpoint + a Grade button in the UI.

**Test coverage:** 8 smoke (SMK-01..08), 11 regression (REG-01..09 incl. ladder
unlock, director fire-once + OCP, grader weighting/clamping), 2 non-gating evals.
`make test` → 23 passed, 2 deselected.

**Deferred to Wave 4 (hardening & handoff):**
1. **Grader calibration** (Epic G3) — compare `LLMGrader` output to human scores
   across ≥10 fixtures before any score is shown to a real user. This is the
   validity gate; until it passes, treat scores as directional only.
2. **A second scenario** to prove "change the client, keep the environment" for
   real (the schema already supports it).
3. **Concurrency & hosting seams** — the app is single-process/single-user by
   design; document (don't yet build) the containerized environment and
   multi-session path. The ports (`repository`, `state`, `llm`, `build_record`)
   are the swap points.
4. **Reveal-ladder eval expansion** — grow EVAL-01's adversarial probe bank and
   add EVAL-03 (long-session character consistency).

---

## 12. Wave 4 status (hardening & handoff)

**Delivered**
- **Grader calibration harness (Epic G3)** — pure validity/reliability metrics
  in `core/grading/calibration.py` (total MAE, bias, within-tolerance rate,
  Spearman rank correlation, self-consistency stdev) with a `CalibrationThresholds`
  gate; a runner + CLI (`python -m sim.app.calibrate`); 5 seed fixtures spanning
  the quality range; and a `calibrated:false` flag on `/grade` so no score is
  shown as decision-grade until the gate passes. Metrics are covered by
  deterministic tests (CAL-01..06); the verdict needs a real model + real human
  scores.
- **Second scenario** (`support_copilot`) — a RAG / applied-AI discovery problem
  reusing the same engine with zero code change (SMK-09), proving "change the
  client, keep the environment".
- **Hosting seams** — `docs/HOSTING.md` maps every scaling concern to an existing
  port; nothing in the core changes to go multi-user.
- **Eval expansion** — EVAL-03 (long-session character consistency) added.

**Test coverage now:** 9 smoke, 16 regression (incl. CAL-01..06, build-record),
3 non-gating evals. `make test` → 31 passed, 3 deselected.

**What still stands between this and a score you'd stake a decision on**
1. Run `python -m sim.app.calibrate` against a **real model** with **real
   instructor scores** in the fixtures (the seed human scores are placeholders).
   This is an ops/content task, not a code task. Only after it PASSES do you set
   `GRADER_CALIBRATED=true`.
2. Build the **containerized environment** (the "real computer" from the pitch) —
   the one genuinely new adapter, behind a new `Environment` port. Everything
   else needed for hosting is a swap of an existing port (see `docs/HOSTING.md`).

---

## 13. Wave 5 (spike) — the per-session environment

Status: **spike, proven**. Sessions can now go beyond plan-only.

**Delivered**
- `Environment` port (`provision`/`handle`/`teardown`) + a `LocalFolderEnvironment`
  adapter that seeds a per-session folder from the scenario's `starter/` template
  and git-baselines it.
- A real starter repo for `churn_dashboard` with the messy Postgres/Stripe
  no-join-key pain baked in (the hidden constraint made tangible).
- Web endpoints (provision/handle/teardown) + a Workspace button; the `/grade`
  endpoint auto-reads the sandbox's git build record when none is supplied, so
  the tester's actual work is graded.
- Tests ENV-01..04 (seed/idempotent/teardown/no-template/build-record loop) and
  SMK-10 (provision through the API). Full suite: 43 passed, 3 deselected.

**Deliberately not built (this is a spike):** isolation/security, remote/multi-
machine, a provisioned agent. The tester uses their own agent on their own
machine. See `docs/SPIKE_ENVIRONMENT.md`.

**The one real engineering investment left:** a `DockerEnvironment` adapter
behind the same port, for isolation. Worth doing only once playtests confirm the
build-for-real loop beats plan-only — which is exactly what this spike lets you
test cheaply first.

---

## 14. Wave 5b — Docker environment (the real dev flow)

Plan-only was scaffolding to de-risk the conversation loop; the real product
puts the tester in a real environment (the flight-sim / hospital-rounds
analogy), with the AI personas as the client/mentor/stakeholder.

**Delivered**
- `DockerEnvironment` adapter behind the existing `Environment` port: a
  per-session container, starter repo bind-mounted at `/workspace`,
  git-baselined, with memory/cpu/pid limits. Selected via `ENV_PROVIDER=docker`
  — zero changes to core, grader, web, or build observer (verified).
- Docker commands go through an injectable runner, so lifecycle is tested
  without a daemon (DOCK-01..05: provision/bind-mount/idempotent/teardown/
  run-failure/missing-docker).
- Web + UI surface the container name and the `docker exec` connect hint;
  provision errors return 503 (docker down) / 500 (run failed) instead of a
  stack trace. `/grade` still auto-reads the host git build record unchanged.
- `docs/ENVIRONMENT.md` covers running real sessions, config knobs, and the
  honest isolation limits.

**Full suite: 48 passed, 3 deselected.**

**Remaining hardening (not blocking real playtests):** stricter isolation
(rootless/gVisor, seccomp, `--network none` where the task allows) before
untrusted users; multi-host autoscaling (see `docs/HOSTING.md`). Both are
adapter/ops work behind ports that already exist.

---

## 15. Wave 7 — Files & Tickets (immersion surfaces)

Two more desktop apps, each a real surface behind the established patterns.

**Files** — `WorkspaceReader` port + `LocalWorkspaceReader` adapter (path-safe,
read-only). Resolves the sandbox workdir via the `Environment` port; the app is a
breadcrumb + listing + viewer. Tests FILES-01..05 incl. traversal blocked.

**Tickets** — `TicketStore` port + sqlite/memory adapters + `TicketService` that
lazy-seeds from the scenario's `tickets:`. A 3-column board (To Do / In Progress /
Done); create and move. Create/move are recorded in the transcript (kind 'ticket')
so scoping is gradeable. Tests TK-01..04.

Neither touched the conversation core. Full suite: 66 passed, 3 deselected.

**Future seam:** a director `ticket` action (scope-creep as a new inbound ticket),
mirroring the email event — deliberately left unbuilt in v1.

---

## 16. Wave 8 — Instructor replay view

A gated `/instructor` page: session picker, a scrubbable/playable timeline that
unifies every surface (chat, mail, tickets, reveals, joins) in chronological order
with surface filters, and on-demand grading with evidence. Pure read-over-data —
the transcript already records everything, so no new capture was needed.

Auth is a **light password gate** (`INSTRUCTOR_PASSWORD`, default `$T0mV13w`):
a shared secret checked in one place, cleartext over HTTP. Explicitly NOT real
auth — documented as such in `docs/INSTRUCTOR.md`; swapping in accounts/HTTPS is
contained to `create_web_app`. Tests: SMK-14 (wrong password rejected, missing
token 401, valid token lists sessions + returns replay). Full suite: 67 passed.

---

## 17. Director → ticket (scope-creep beat)

The director can now file a ticket, not just chat/email — a third action kind
routed through `SessionService` to `TicketService.file_from` (persona-attributed,
recorded in the transcript, announced as a chat signal, fires once). The churn
scenario now escalates across three surfaces: Marcus joins chat (turn 3), Priya
files a scope-creep ticket (turn 4), Dana emails a budget constraint (turn 5).

Fixed along the way: ticket seeding is now idempotent-by-title and runs at session
start, so a director ticket arriving first can't suppress the seeded backlog
(regression TK-05). Full suite: 69 passed, 3 deselected.

---

## 18. Initiative: Adaptive difficulty & instructor control

**Core model — two axes, never conflated:**
- **Scenario difficulty** — a property of a scenario (`intern`…`distinguished`): what level it's *pitched at*. Stops a junior getting a staff problem; a mismatch is surfaced, not hidden.
- **Engineer level** — the instructor's per-session setting. Shapes **pressure**, **persona posture**, and the **grading bar** (grade to expectations, not a flat number).

Levels: `intern, junior, mid, senior, staff, principal, distinguished`.

### Epics
- **J — Level & difficulty model.** Level profiles (pace, posture, weight/bar shifts, expectation), scenario `difficulty` tag, difficulty↔level matching.
- **K — Settings & onboarding.** Durable instructor settings + per-session settings; first-run onboarding with level-derived sane defaults.
- **L — Adaptive pressure & personas.** Level scales director beat timing/count (+ per-trigger `min_level`); persona system prompts gain a posture layer.
- **M — Expectation-based grading.** Level shifts rubric weights + passing bar + a grader "expectation" note. Mechanism honest, **validity behind `calibrated:false`** until per-level calibration is run.
- **N — Multi-scenario & assignment.** Scenario registry; per-session scenario resolution (a `SessionManager`); assign a scenario+level to a session.
- **O — Instructor Dashboard.** The gated area becomes a dashboard: onboarding (first-run only), New-session setup (pick scenario by difficulty + level + overrides → session link), Settings (set/reset/update levels & defaults), Sessions + Replay (existing).
- **P — Scenario library.** At least one scenario per engineer level.

### Waves
- **Wave 9 — Adaptive foundation** (J + K-backend + L). Level profiles, difficulty tags, settings store (instructor + session), level-scaled pressure, persona posture. *Build first.*
- **Wave 10 — Expectation grading** (M). Level-adjusted rubric + expectation note, calibration-gated.
- **Wave 11 — Multi-scenario** (N). Registry + `SessionManager` + per-session scenario; the "assign a scenario" refactor.
- **Wave 12 — Instructor Dashboard** (O). Onboarding page, new-session setup, settings, over the sessions/replay view.
- **Wave 13 — Scenario library** (P). A scenario per level (content; ongoing).

### Selected stories (abbreviated)
- *As an instructor, on first run I'm onboarded* — I pick a default engineer level and get sane defaults, and I'm not asked again. (K)
- *As an instructor I set/change a session's level* — before the trainee starts, and can update it later. (K, O)
- *As an instructor I pick a scenario suited to a level* — scenarios show their difficulty; a mismatch warns me. (J, N, O)
- *As a trainee I feel level-appropriate pressure* — an intern gets one gentle stakeholder, spaced out; a staff engineer gets overlapping stakeholders and a curveball. (L)
- *As a trainee the personas treat me per my level* — patient-mentor for juniors, terse-adversarial for seniors. (L)
- *As an instructor the grade reflects expectations* — same criteria, level-shifted weights/bar, clearly flagged uncalibrated. (M)

### Stretch (captured, not planned)
- **Real Slack (or an OSS Slack clone) as the chat transport**, personas posting into it for maximum authenticity. Honest tradeoff: gains realism, **loses the single-transcript control** that grading + replay depend on — it's a "replace the transport, keep the engine" project (message capture, threading fidelity, data egress for grading), not a bolt-on. Possible behind the existing channel/transport seams; genuinely more work than it looks.

### Wave 9 status — DONE (adaptive foundation + expectation-grading mechanism)

Delivered: `core/levels.py` (7 level profiles: pace, posture, weight-shift, expectation); scenario `difficulty` tag + per-trigger `min_level`; level-aware director timing/gating; persona **posture** layer threaded through chat + mail; `SettingsStore` (instructor onboarding row + per-session level) with sqlite/memory adapters; endpoints (`/api/levels`, get/set session level, get/set instructor settings — gated); and **level-aware grading** (rubric weights shifted + an expectation note), still behind `calibrated:false`. Backward compatible: unset level defaults to `senior` = prior behaviour.

Verified end-to-end: intern gets only the VP; mid adds the scope-creep ticket; senior+ adds the budget email; posture lands in every prompt. Tests LEVEL-01..06, SMK-15. Full suite: 76 passed, 3 deselected.

Next: Wave 11 (multi-scenario registry + `SessionManager` + assignment) then Wave 12 (instructor dashboard UI over onboarding/new-session/settings) then Wave 13 (a scenario per level). Wave 10's grading mechanism shipped here; its *validity* still needs per-level calibration runs.

### Wave 11 status — DONE (multi-scenario)

The app went from one-scenario to many. `build_registry` loads every `scenarios/*/scenario.yaml`; a `SessionManager` resolves each session to its assigned scenario (via `SettingsStore.get_session_scenario`, default `churn_dashboard`) and hands out a per-scenario **Bundle** (session/mail/ticket services + environment), cached by scenario key. Shared stores (transcript, unlock, mail, tickets, settings — one SQLite file, keyed by session_id) are built once; grader/build-observer/file-reader stay app-global.

The web layer now resolves a bundle per request; `/api/scenarios` lists options with difficulty, `/api/session/{id}/scenario` returns the session's scenario, and `POST /api/instructor/session/{id}/scenario` assigns one (gated). Verified: two sessions run different scenarios (churn/Priya and support_copilot/Dev) concurrently, each with its own cast. Tests MULTI-01..04, SMK-16. Full suite: 81 passed, 3 deselected.

Next: Wave 12 — the instructor dashboard UI (onboarding-on-first-run, new-session setup that assigns scenario+level and hands over a link, settings) over the existing gated replay view. All its endpoints now exist.

### Wave 12 status — DONE (instructor dashboard)

`/instructor` is now a dashboard, not just a replay viewer: first-run onboarding (sets default level, `onboarded`), a New-session screen (pick scenario w/ difficulty + level, difficulty↔level match warning, creates the session via the assignment endpoints and produces a copyable trainee link), a Sessions list (scenario + level badges) into the scrubbable replay + grade, and Settings (default level, scenario library, reset onboarding). Pure frontend over Wave 9/11 endpoints. Page + flow verified; full suite 81 passed.

Remaining in the initiative: Wave 13 — a scenario per engineer level (content), and Wave 10's grading *validity* (per-level calibration runs). Both are content/ops, not new architecture.

### Wave 13 status — DONE (scenario library, one per level)

Authored five new scenarios so every engineer level has at least one, spanning a
deliberate complexity gradient: intern (a scoped signup bug — the fix isn't where
the client thinks), junior (help-center 'search' that's really top-FAQs), staff
(a deploy pipeline where the real problem is flakiness + ownership, with scope-creep
and budget beats), principal (build/buy feature flags — really consolidation +
migration + politics, with a defensive incumbent engineer), and distinguished (an
ML-platform 'bottleneck' that's actually an incentive/org problem, two warring VPs,
and a governance curveball). Each uses the shared four-criterion rubric so level
weight-shifts apply, gates its stakeholder beats by `min_level`, seeds a backlog,
and ships a starter repo. Loaded automatically by the registry — zero code changes.
Tests LIB-01..03, SMK-17. Full suite: 84 passed, 3 deselected.

The adaptive-difficulty initiative (Waves 9-13) is now feature-complete. What
remains is validation, not construction: real playtests per level and per-level
grader calibration (the grader still, correctly, flies `calibrated:false`).
