# From local MVP to hosted

Hosted stack is **Railway (uvicorn) + Firebase Auth + Firestore**. Detail and
waves: `DEPLOYMENT-PLAN.md`. Identity build order: `auth-plan.md`.

Local/LAN stays `AUTH_MODE=password` and `PERSISTENCE=sqlite` unless you opt in.

## What changes, and where

| Concern | Local default | Hosted | Swap point |
|---|---|---|---|
| Identity | instructor password | Firebase email | `ports/identity.py`, `AUTH_MODE` |
| Transcript / mail / tickets / settings / users / sessions | SQLite file | Firestore collections | existing ports + `PERSISTENCE=firestore` |
| Model calls | Ollama / Groq / Anthropic env | same adapters; challenger Groq key in Settings (H2) | `ports/llm.py` + `BYOK_SECRET` |
| Build record | local git | learner patch / GitHub submit (no Railway sandbox) | `ports/build_record.py` |
| Transport | one uvicorn | one Railway replica, HTTPS + `wss://` | `adapters/web` |

`sim/core/` imports none of these (`test_smk02`).

## Not on the first Railway deploy

- Server-side Docker / code-server workspaces
- Postgres
- Firebase Hosting as the API
- More than one Railway replica (in-process WebSockets)
