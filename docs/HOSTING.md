# From local MVP to hosted

Hosted stack is **Railway (uvicorn) + Firebase Auth + Firestore**. Detail and
waves: `DEPLOYMENT-PLAN.md`. Identity build order: `auth-plan.md`.

Local/LAN stays `AUTH_MODE=password` and `PERSISTENCE=sqlite` unless you opt in.

## What changes, and where

| Concern | Local default | Hosted | Swap point |
|---|---|---|---|
| Identity | instructor password | Firebase email | `ports/identity.py`, `AUTH_MODE` |
| Transcript / mail / tickets / settings / users / sessions | SQLite file | Firestore collections | existing ports + `PERSISTENCE=firestore` |
| Model calls | Ollama / Groq / Anthropic env | same adapters; challenger's own Groq key from Settings wins | `ports/llm.py` + `BYOK_SECRET` |
| Workflow | build scenarios use a server dev box (`sandbox`) | build scenarios use a linked public GitHub repo (`repo`); design scenarios are in-browser (`doc`) everywhere | `sim/core/workflow.py`, `WORK_MODE` |
| Build record | local git | GitHub or GitLab commits + `DESIGN.md`/`README.md` text (challenger's own token wins) | `ports/build_record.py`, `ports/repo_host.py`, `GITHUB_TOKEN`, `GITLAB_URL`/`GITLAB_TOKEN` |
| Browser edits | sandbox folder | `session_files` overlay in Firestore, replayed onto a fresh folder after a redeploy | `ports/session_files.py` |
| Grades | sqlite `grades` | `sessions/{sid}/grades/latest` | `ports/grades.py` |
| Dashboards | direct reads | session index on the session doc + 60 s stale-while-revalidate cache | `_enrich_sessions`, `_cached` in `adapters/web/app.py` |
| Transport | one uvicorn | one Railway replica, HTTPS + `wss://`, static served `no-cache` | `adapters/web` |

`sim/core/` imports none of these (`test_smk02`).

Repo hosts (GitHub, plus one GitLab instance via `GITLAB_URL`) and the Connect
GitHub / GitLab OAuth apps are described in `docs/REPO-HOSTS.md`.

## Not on the first Railway deploy

- Server-side Docker / code-server workspaces
- Postgres
- Firebase Hosting as the API
- More than one Railway replica (in-process WebSockets)
