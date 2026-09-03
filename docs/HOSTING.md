# From local MVP to hosted (Wave 4 seams, not yet built)

The MVP is single-process, single-user, no-auth by design. Going multi-user does
NOT require rewriting the core — every scaling concern maps to a port that
already exists. This doc records the swap points so the work is bounded.

## What changes, and where

| Concern | Today (MVP) | Hosted | Swap point (port) |
|---|---|---|---|
| Transcript store | `SqliteMessageRepository` (one file) | Postgres, one row-set per session | `ports/repository.py` |
| Unlock state | `SqliteUnlockStore` | same Postgres | `ports/state.py` |
| Model calls | in-process Ollama/Anthropic | same, but with rate limiting + retries in the adapter | `ports/llm.py` |
| Build record | local git via `GitBuildObserver` | a cloned repo in the session's container, or a git host API | `ports/build_record.py` |
| The "real computer" | tester's own machine | a per-session container (VM/pod) with the repo + agent | new adapter behind a new `Environment` port |
| Transport | one FastAPI process | same app, many workers behind a load balancer | `adapters/web` (unchanged core) |

Because `sim/core/` imports none of these (enforced by SMK-02), swapping any row
is an adapter + composition-root change only.

## The three things to actually build for hosting
1. **Per-session isolation.** Repositories are already keyed by `session_id`;
   move them to Postgres and add auth so a tester only sees their own session.
2. **Concurrency.** `post_tester_message` is synchronous and offloaded via
   `run_in_threadpool`; under real load, move LLM/grader calls onto a queue and
   make the WebSocket handler push results as they complete. No core change.
3. **The containerized environment** (the "real computer" from the pitch). This
   is the one genuinely new adapter: provision a sandbox per session with the
   starter repo + the tester's coding agent, and point `BuildRecordSource` at it.

## Explicitly out of scope until calibration passes
Do not scale the grader before `python -m sim.app.calibrate` passes on real
human-scored fixtures. Shipping an uncalibrated score to many users is worse
than shipping it to one — the `calibrated:false` flag on `/grade` is the guard.
