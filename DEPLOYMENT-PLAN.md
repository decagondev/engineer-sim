# Deployment Plan — Railway + Firebase

> **Status: stack decided. Identity and Firestore adapters exist locally.
> Railway hosting is the remaining work.** Local/LAN (`AUTH_MODE=password`,
> `PERSISTENCE=sqlite`) stays as-is for the in-room cohort.

Remote students reach a public HTTPS URL. The process is still FastAPI /
`uvicorn`. Identity and durable state live in the existing Firebase project
(`work-sim-79d4d`). The app process lives on Railway. Postgres is **not** in
this plan.

---

## 1. Target stack

| Piece | Vendor | Role |
|---|---|---|
| App process | **Railway** | One container running `uvicorn sim.app.main:app --host 0.0.0.0` |
| Identity | **Firebase Auth** | Email/password; roles in our `users` collection |
| Database | **Cloud Firestore** | Users, sessions, transcripts, mail, tickets, submissions, settings |
| Inference (hosted MVP) | **Groq BYOK** | Each learner pastes their own key (Wave H2; not required to first-deploy) |

**Why this split.** Auth and Firestore are already wired (`AUTH_MODE=firebase`,
`PERSISTENCE=firestore`). Railway runs Python as-is and gives HTTPS without
Firebase Hosting (Hosting cannot run this ASGI process or the chat WebSocket).
Identity and compute do not have to be the same vendor.

**Why not Postgres.** That was the earlier hosted default (SQL-shaped stores).
The Firestore adapters are now the hosted store. SQLite remains the local/test
default. Do not add a third database.

**Why not Firebase Hosting / Cloud Functions.** Static hosting and short
functions cannot keep a WebSocket, long LLM calls, or the FastAPI app. Cloud
Run would also work; Railway is the chosen host.

---

## 2. What is already built

| Capability | Where | Local env |
|---|---|---|
| Email sign-in, three roles, three dashboards | `auth-plan.md` Waves A0–A6 | `AUTH_MODE=firebase` |
| Session ownership + WS token | `sim/core/access/policy.py`, web middleware | same |
| Firestore stores behind existing ports | `sim/adapters/persistence/firestore_store.py` | `PERSISTENCE=firestore` |
| SQLite → Firestore copy | `tools/migrate_sqlite_to_firestore.py` | optional |
| Deny-all Firestore rules | operator (console) | required before public traffic |

Core stays framework-free (`test_smk02`). Railway is composition + ops, not a
domain rewrite.

---

## 3. Guiding principles

1. **Local-first.** Classroom LAN keeps password + sqlite unless you opt in.
2. **Auth before public exposure.** Railway must boot with
   `AUTH_MODE=firebase`. The shared instructor password is not a public gate.
3. **Server is the only Firestore client.** Rules stay `allow read, write: if false`.
   The service account on Railway bypasses rules.
4. **No server-side learner workspaces on Railway.** Patch / GitHub submit only.
   Cloud disks are ephemeral; Docker-in-container is out of scope.
5. **Keys are handled properly.** BYOK (H2) is write-only and encrypted at rest.
   Until H2, a single server `GROQ_API_KEY` / `LLM_PROVIDER` is operator-only
   and never shipped to the browser.
6. **The grader stays honest.** Hosting does not flip `calibrated`.

---

## 4. Waves

| Wave | Name | Goal | Exit criterion |
|---|---|---|---|
| **H0** | Railway + Firestore | Public HTTPS app, same Firebase project, trusted testers only | Redeploy does not wipe data; you sign in as admin; one assigned session completes |
| **H1** | Public-safe identity | Railway hostname authorised; password path dead on this deploy; chat works on HTTPS | Instructor + challenger on the Railway URL; stranger gets 403 on another session |
| **H2** | Bring-your-own-key **(hosted MVP)** | Learner Groq key in Challenger → Settings | Remote learner sets a key and finishes a graded session without the key echoing back |
| **H3** | Scale & safety | Queue + quotas for measured concurrency | Bursts queue; one user cannot wedge the box |
| **H4** | Durability & privacy | Backups, deletion, cost, incident notes | You can answer where data lives, how to delete it, and what a cohort costs |

H0 and H1 are close together because Auth + Firestore already exist. H0 is
“it is on Railway.” H1 is “it is safe to give a student the URL.”

---

## 5. Epic Q — Identity (mostly done)

Implementation detail: `auth-plan.md`. Hosted leftovers only:

- **Q-host-1.** Firebase Auth → **Authorized domains** → add the Railway
  hostname (`*.up.railway.app` and any custom domain). `localhost` stays.
- **Q-host-2.** Hosted boot: `AUTH_MODE=firebase` required. Missing project /
  web API key / credentials → refuse to start (already true for firebase mode).
- **Q-host-3.** Password reset / verification templates must use an authorised
  domain (Railway URL or a custom domain you own).

LAN may keep `AUTH_MODE=password`. The Railway service must not.

---

## 6. Epic R — Firestore (adapters done; ops remain)

Collections (server-written only):

```
users/{uid}
sessions/{session_id}                  # registry + level/scenario + message_count
sessions/{session_id}/messages/{seq}
sessions/{session_id}/unlock/{persona}
sessions/{session_id}/mail/{thread_id}
sessions/{session_id}/tickets/{ticket_id}
sessions/{session_id}/submissions/{seq}
meta/instructor
scenario_config/{scenario_key}
```

**R-host-1.** Console: Firestore Native, production rules deny-all (see §9).
**R-host-2.** Service account JSON in Railway **Variables** as the inline
JSON string (see T2). Never in the GitHub repo.
**R-host-3.** Optional one-shot: `python tools/migrate_sqlite_to_firestore.py`
from a machine that can see both `sim.db` and the service account.
**R-host-4 (H4).** Firestore PITR / daily export; a tested restore note.
**R-host-5.** Document 1 MB max per Firestore doc — huge patches may need a
later object-store slice; not H0.

No Alembic, no Railway Postgres plugin, no `DATABASE_URL`.

---

## 7. Epic T — Railway

**T1 — Container (H0) — done**
- `Dockerfile`: Python 3.12-slim + git, `pip install -r requirements.txt`,
  uvicorn on `$PORT` with `--proxy-headers` (Railway injects `PORT`).
- `.dockerignore`: `.sandboxes/`, `sim.db`, `*-firebase-adminsdk-*.json`,
  `.git`, tests, docs.
- `railway.toml`: Dockerfile builder, `/health` healthcheck, one replica.

**T2 — Variables (H0)** — set on the Railway service, not in git:

```
AUTH_MODE=firebase
PERSISTENCE=firestore
FIREBASE_PROJECT_ID=work-sim-79d4d
FIREBASE_WEB_API_KEY=...
FIREBASE_AUTH_DOMAIN=work-sim-79d4d.firebaseapp.com
AUTH_BOOTSTRAP_ADMIN_EMAIL=tom@decadev.co.uk
FIREBASE_CREDENTIALS_JSON={"type":"service_account",...}
  # paste the whole service-account JSON as one Railway variable;
  # a file path or GOOGLE_APPLICATION_CREDENTIALS also work
LLM_PROVIDER=groq
GROQ_API_KEY=...          # operator key until H2
PUBLIC_BASE_URL=https://worksim.decadev.co.uk   # optional; set-password emails
GITHUB_TOKEN=ghp_...            # read-only; raises the GitHub API limit for repo browsing
WORK_MODE=auto                  # auto|local|hosted; auto = hosted when Firebase/Firestore is on
  # link back here. Omitted, the app uses the host of incoming requests.
```

Do not set `AUTH_MODE=password` on Railway.

**T3 — HTTPS (H0)**
- Railway public URL is HTTPS. Health: `GET /health`.

**T4 — WebSocket on HTTPS (H0 / H1) — done**
- `sim/adapters/web/static/apps/chat.js` opens `wss://` when
  `location.protocol === "https:"`, `ws://` otherwise.

**T5 — Health & logs (H3)**
- `/health` already exists. Railway logs + a “Groq 429” breadcrumb are enough
  until measured load says otherwise.

**T6 — Backups (H4)**
- Firestore managed export / PITR, not a Railway volume. App disks are
  disposable.

**T7 — Scale (H3)**
- Start with **one replica**. The process holds in-memory WebSockets and
  sandbox paths; multi-instance needs sticky sessions or moving chat off
  process memory. Do not flip replicas until that is designed.

---

## 8. Epic S — Bring-your-own-key (H2)

Challenger → Settings lets a signed-in learner set their display name and a
Groq key. The key is Fernet-encrypted (`BYOK_SECRET`, or a derived local
secret) on the user record. APIs expose `has_groq_key` only — never the
plaintext or ciphertext. Chat, mail, unlock, and grading resolve the current
uid and use that key when present; otherwise the server `GROQ_API_KEY`.

Validate on save against Groq. Mid-session 401/429 tell the learner to check
Settings. Link: `https://console.groq.com/keys`.

Set `BYOK_SECRET` in production so rotating the instructor password does not
orphan stored keys.

---

## 9. Operator checklist (do these in order)

### Firebase console (once)

1. Auth: Email/Password enabled (already, if local firebase login works).
2. Firestore Database created (Native, production).
3. Rules published:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

4. Service account private key generated; file kept off-repo.
5. After Railway gives you a URL: Auth → Settings → **Authorized domains**
   → add that host.

### Railway (H0)

1. New project → deploy this repo (or `railway up` from a Dockerfile).
2. Set the variables in §7 T2. Put the service-account JSON in Railway
   secrets, not in the repo.
3. Confirm `https://<service>.up.railway.app/health` returns `{"status":"ok"}`.
4. Confirm `/login` signs in against `work-sim-79d4d`.
5. Admin → Settings shows **store firestore**.
6. Fix and verify Team Chat over `wss://` (T4).

### Do not

- Enable a Railway Postgres plugin “for later.”
- Open Firestore to the web API key.
- Commit `*-firebase-adminsdk-*.json`.
- Point students at the URL before authorized domains + H1 checks.

---

## 10. Cross-cutting

- **Security:** HTTPS; firebase gate; deny-all Firestore; secrets only on Railway.
- **Privacy:** GDPR-style deletion is H4 (`users` + `sessions/{id}` cascade).
- **Reliability:** Firestore outlives a Railway redeploy. The container does not
  hold the source of truth.
- **Cost:** Railway compute + Firestore + (until H2) your Groq bill. Measure a
  cohort before adding replicas or a queue.
- **Operability:** one operator, one replica, Railway logs, Firebase console.

## 11. Definition of Done (per story)

1. Behind a port; `sim/core` unchanged.
2. Tests on fakes (sqlite / `AUTH_MODE=fake`); no live Firebase required in CI.
3. Works on Railway, not only `localhost`.
4. LAN password + sqlite still default when env is unset.

## 12. Out of scope

- Firebase Hosting as the app server.
- Railway Postgres / Alembic.
- Server-run code-server / Docker sandboxes for remote learners.
- Multi-region, autoscaling, replica > 1 (until WebSockets are share-nothing).
- Grader calibration (orthogonal).
- Google / SSO (Firebase can add later; same verifier).

## 13. Decisions

| Decision | Why | Trade-off |
|---|---|---|
| Firestore, not Postgres | Adapters exist; same project as Auth; no extra DB on Railway | No SQL aggregates; 1 MB doc limit; seq counters are read-max+1 |
| Railway, not Firebase Hosting | Needs a real ASGI process + WebSockets | Two vendors (Railway + Google) |
| Firebase Auth | Already shipped; no custom password DB | Vendor lock on identity |
| One Railway replica | In-process WebSockets | Horizontal scale is a later design |
| BYOK Groq at H2 | Cost and ban-risk stay with the student | Extra onboarding; H0 may use an operator key |

## 14. Sequencing

1. Keep LAN on password + sqlite for the room.
2. Finish Firebase console (§9) if Firestore is not created yet.
3. **H0:** Dockerfile + Railway variables + `wss://`.
4. **H1:** authorised domain; two real accounts on the public URL.
5. Run a tiny remote cohort. Measure concurrency and Groq spend.
6. **H2** when remote learners should not share your key.
7. **H3 / H4** only when the numbers say so.
