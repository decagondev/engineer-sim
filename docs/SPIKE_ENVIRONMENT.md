# Spike notes: the per-session environment

> UPDATE: the Docker adapter described as the "hardening path" below is
> **NOW IMPLEMENTED** (`sim/adapters/environment/docker.py`). See
> `docs/ENVIRONMENT.md` for how to run real build-for-real sessions. This
> file is kept as the original spike rationale.

# Spike: the per-session environment (the "real computer")

This is a **spike**, not production. It exists to prove one thing before we
dedicate engineering to it: that we can give a tester a real per-session
workspace seeded from a scenario, let them build in it with their own tools, and
capture that work as the build record the grader uses — closing the loop from
"talk to the client" to "ship something and be graded on it".

## What the spike proves (and it does)
- A session provisions a folder from the scenario's `starter/` template.
- The tester opens it in **their own editor / coding agent** and works normally.
- Their git history (starter baseline → their commits) is captured automatically
  and fed to the grader at grade time — no manual export.

Demonstrated end to end: provision → build + commit → `/grade` auto-reads the
diff → the tester's files reach the grader.

## What it deliberately is NOT
- **Not isolated / not a security boundary.** A local folder is a working
  directory. Do not run untrusted code in it. This is fine for trusted
  playtesters on their own machine; it is not fine for the open internet.
- **Not remote / not multi-machine.** Single host, single user.
- **No provisioned agent.** The tester brings their own (Cursor, Claude Code,
  plain editor). The sim only hands them the path.

## The hardening path (same port, drop-in)
Everything above sits behind the `Environment` port
(`sim/core/ports/environment.py`: `provision` / `handle` / `teardown`). To make
it real you write **one new adapter** — `DockerEnvironment` — that provisions a
container per session with the starter repo inside, and returns a handle whose
`workdir` points into that container. Nothing in the core, the web layer, the
grader, or the build observer changes. That isolation work is the actual
engineering investment this spike is meant to justify — and it's only worth
doing once playtests confirm the build-for-real loop adds enough over plan-only
sessions to be worth it.

## Try it
```
set LLM_PROVIDER=ollama&& set OLLAMA_MODEL=llama3.1:8b&& python -m uvicorn sim.app.main:app
```
Click **Workspace** to provision, open the printed path in your editor, build and
commit, then click **Grade run** — the grade includes your git work. Sandboxes
live under `SANDBOX_ROOT` (default `.sandboxes/`); delete the folder or call the
teardown endpoint to reset.
