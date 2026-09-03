# The per-session environment (real build-for-real)

Sessions are build-for-real, not plan-only: each one gets an isolated dev
environment seeded from the scenario's starter repo, the tester works in it with
their own agent, and their git history is graded. This is the "rounds in a real
hospital" part — the AI personas are the client/manager/stakeholder, the
environment is real.

Two adapters, one `Environment` port (`provision` / `handle` / `teardown`):

| Adapter | Isolation | Needs | Use for |
|---|---|---|---|
| `local_folder` (default) | none (a working dir) | nothing | quick local runs, CI, machines without Docker |
| `docker` | real container (process + fs boundary, mem/cpu/pid limits) | Docker Desktop running | actual playtests / real sessions |

Selecting one is a config swap — no code changes anywhere:
```
set ENV_PROVIDER=docker
```

## Running a real session with Docker

1. Install & start **Docker Desktop**. First run pulls the image
   (`python:3.11-slim` by default) — that happens on first provision.
2. Start the app with a real model + docker env:
   ```
   set LLM_PROVIDER=ollama&& set OLLAMA_MODEL=llama3.1:8b&& set ENV_PROVIDER=docker&& python -m uvicorn sim.app.main:app
   ```
3. In the UI, click **Workspace**. The app provisions a container
   (`sim-<session>`), seeds the starter repo, git-baselines it, and shows you:
   ```
   docker exec -it sim-<session> bash   # your files are in /workspace
   ```
4. The starter also lives on the host under `.sandboxes/<session>/`, bind-mounted
   to `/workspace` in the container. So you can:
   - edit on the host with your own editor / coding agent (Cursor, Claude Code), and
   - run/test code isolated inside the container via the `docker exec` shell.
5. Commit as you go (on the host, or in the container if the image has git).
6. Click **Grade run** — the grade auto-reads your git history as the build record.

## How it's wired (bind-mount model)
- Host `.sandboxes/<session>/` is the source of truth, git-initialised with a
  `scenario starter (baseline)` commit.
- The container mounts it at `/workspace` and runs `sleep infinity` so it stays
  up for the session. Code executes in the container; files live on the host.
- The git build observer reads the **host** path unchanged — no change to the
  grader or build record to support Docker.

## Config knobs (env vars)
```
ENV_PROVIDER=docker|local_folder     SANDBOX_ROOT=.sandboxes
SANDBOX_IMAGE=python:3.11-slim       SANDBOX_MEMORY=2g
SANDBOX_CPUS=2                       SANDBOX_PIDS=512
```
A scenario can override the image with an `image:` field.

## Honest limits
- The container is a real execution boundary, not a hardened multi-tenant
  sandbox against a determined adversary. Fine for trusted trainees; add stricter
  isolation (rootless/gVisor, `--network none` where the task allows, seccomp)
  before exposing it to untrusted users.
- Single host. Multi-machine / autoscaling is the hosting step in
  `docs/HOSTING.md` — and it's still just adapter swaps behind the same ports.
- Windows: Docker Desktop must have file sharing enabled for the drive the repo
  lives on, so the bind mount works.

## Lifecycle & cleanup
- `POST /api/session/<id>/environment/teardown` removes the container and the
  host dir. Or `docker rm -f sim-<id>` and delete `.sandboxes/<id>/`.
- Sandboxes and `.sandboxes/` are git-ignored; they're ephemeral.
