# Deployment Plan — Hosted Version (future stretch)

> **Status: planning only. Nothing here is built.** This is the roadmap for
> taking the local/LAN simulator to a hosted service for remote students, built
> *alongside* the local version, not replacing it.

The local (single-machine) and LAN/classroom (Version A) setups stay exactly as
they are. This plan adds a hosted deployment for students who aren't on your
network — reached, not scaled: modest cohorts (20 today, up to a few hundred
later), grown into measured evidence rather than guessed at.

---

## 1. Why this is a bounded project, not a rewrite

Every piece below lands on a **seam that already exists** in the codebase. That
was the point of the hexagonal discipline from Wave 0. Hosting is filling in
adapters and adding one auth layer — the domain (personas, reveal ladders,
director, scenarios, grading) does not change.

| Hosted concern | The seam it uses today | Nature of the work |
|---|---|---|
| Real accounts | the single auth check in `create_web_app` (`_instr_ok`) | **New** (one middleware) |
| Persistent DB | `MessageRepository` / `MailStore` / `TicketStore` / `SettingsStore` / `SubmissionStore` / unlock-state ports | **Port** (SQL→SQL) |
| AI inference | `LLMClient` port + `SessionManager` client construction | **Config → per-user** |
| Concurrency | `run_in_threadpool` around LLM calls | **Add a queue** |
| Public transport | the `--host 0.0.0.0` the LAN server already uses | **Deploy** |

## 2. Target stack (decided, with rationale)

- **Firebase Auth** — identity. Replaces the shared instructor password with real
  accounts. Chosen because building auth from scratch is the scariest hosting
  chore and a managed provider removes it. Identity and database don't have to be
  the same vendor — this is a common, fine split.
- **Railway Postgres** — database. Chosen over Firestore deliberately: the
  storage adapters are **already written in SQL**, so a Postgres port is close to
  mechanical (swap `sqlite3`→`psycopg`, dialect nits for upsert/autoincrement).
  The two patterns that were awkward in Firestore — the instructor "list all
  sessions" aggregate and the per-store sequence counters — are **native** in
  Postgres. Firestore would have meant re-modelling every store as NoSQL
  documents; Postgres keeps the DB on the *easy* side of the fork.
- **Groq, with per-user keys (bring-your-own-key)** — inference. **This is the
  centerpiece.** Each student enters their own free Groq key in Settings; their
  sessions run on their own allowance. This is legitimate (each key is the
  student's own, under their own agreement — exactly the community-center model
  where 400 students each use their own free account), it's free for you and the
  student, it scales with the cohort (each new student brings their own
  allowance), and it removes both the single-point-of-failure of a shared server
  key and the ban risk of pooling free keys. Groq stays behind the `LLMClient`
  port, so this is the same seam as `LLM_PROVIDER`, made per-session.
- **Railway** — hosting the FastAPI app. It runs `uvicorn`; deployment is
  plumbing, not architecture.

## 3. Guiding principles (non-negotiable)

1. **Local-first is preserved.** The hosted build is additive. The in-room cohort
   keeps using the LAN server; the hosted version serves remote students.
2. **Auth before public exposure.** The shared-password gate is *inadequate* (not
   just weak) the moment the app is on the public internet. Real auth lands before
   any student who isn't you can reach it.
3. **Keys are handled properly, never quickly.** A UI that collects API keys is
   exactly where "quick" becomes "incident." The security requirements in §7 are
   mandatory, not optional polish.
4. **Build into evidence.** Don't build a wave until real cohorts show the need.
   Measure actual peak concurrency (likely far below headcount — students code
   locally and think between messages) before hardening for scale.
5. **The grader stays honest.** Hosting changes nothing about grading validity —
   it remains `calibrated:false` until per-level human calibration is run. That's
   a separate, orthogonal effort.

---

## 4. Backlog hierarchy (same shape as `PLANNING.md`)

- **Wave** — a delivery increment; independently deployable, with an exit criterion.
- **Epic** — a major capability.
- **Feature** — a shippable chunk of an epic.
- **User Story** — `As a <role> I want <goal> so that <reason>` + acceptance criteria.
- **Slice** — a thin vertical task delivering something demonstrable.

**Roles:** **Learner** (remote student), **Instructor** (creates/reviews sessions),
**Operator** (runs the hosted service — may be the same person as the instructor),
**Developer** (builds it).

---

## 5. Waves (delivery increments)

| Wave | Name | Goal | Exit criterion |
|---|---|---|---|
| **H0** | Deployable core | Runs on Railway + Postgres, HTTPS, but only trusted testers (still password-gated). | The app is live on Railway with Postgres behind HTTPS; data survives a redeploy; a trusted tester completes a session. |
| **H1** | Real identity | Firebase Auth; accounts; roles; ownership; retire the shared password. | An instructor and a learner sign in with real accounts; sessions are owned and private; the shared password is gone. |
| **H2** | Bring-your-own-key **(hosted MVP)** | Learners run on their own Groq key, entered securely in Settings. | A remote learner signs up, adds their own free Groq key, and completes a full graded session on it — safely (encrypted, write-only, graceful failure). |
| **H3** | Scale & safety hardening | Handle real concurrency and enforce quotas/abuse limits. | Target concurrency (e.g. 50–200) runs without failures; bursts queue instead of erroring; per-user quotas enforced; load-tested. |
| **H4** | Durability & privacy | Data protection, deletion, backups, cost/ops visibility. | You can honestly answer: where's my data, can it be deleted, what if a key leaks, what does a cohort cost, and is there a backup. |

**Dependency order:** H0 (deployable, trusted-only) → H1 (auth, safe to expose) →
H2 (per-user keys, now identified & safe → remote students can use it) → H3/H4
(grow into these when cohorts justify).

---

## 6. Epics → Features → Stories → Slices

### Epic Q — Identity & access (Firebase Auth) · Wave H1

**Q1 — Token verification**
- *As a Developer, I verify a Firebase ID token in one place so the rest of the app trusts a `uid`.*
  - AC: the check that was `_instr_ok` becomes token verification; no endpoint trusts the client for identity.
  - Slices: verify-token dependency; extract `uid` + role claim; reject unverified.

**Q2 — Login / signup UI**
- *As a Learner, I sign in (email/password or Google) so my sessions are mine.*
- *As an Instructor, I sign in so only I can reach the dashboard.*
  - Slices: login page; Firebase web SDK; session cookie/token handling; sign-out.

**Q3 — Roles & authorization**
- *As an Operator, instructors and learners have different powers so learners can't open the dashboard.*
  - AC: instructor-only endpoints require an instructor role claim.
  - Slices: role claim (custom claims); role guard on instructor routes.

**Q4 — Ownership & tenancy**
- *As an Instructor, I only see sessions I (or my org) own.*
- *As a Learner, my session data is private to me.*
  - AC: records carry an owner `uid`/org; queries are scoped to the caller.
  - Slices: owner column on sessions; scope the instructor session-list; scope replay/grade.

**Q5 — Retire the shared password**
- *As an Operator, the classroom password gate is gone in the hosted build so there's no shared secret in cleartext.*
  - Slices: remove `INSTRUCTOR_PASSWORD` path in the hosted config; keep it for local/LAN only.

### Epic R — Persistent data (Railway Postgres) · Wave H0

**R1 — Postgres store adapters**
- *As a Developer, I run every store on Postgres behind the existing ports so the core is unchanged.*
  - AC: `Postgres{Message,Mail,Ticket,Settings,Submission}Repository/Store` + unlock-state implement the same ports; a `DB=postgres` config selects them.
  - Slices: one adapter per store (port the SQL); driver swap (`psycopg`); upsert/sequence dialect fixes.
  - Note: the aggregate session-list and sequence counters port *easily* here (native SQL), unlike a NoSQL store.

**R2 — Schema & migrations**
- *As an Operator, schema changes are versioned and repeatable.*
  - Slices: migration tool (e.g. Alembic); initial schema; migrate-on-deploy.

**R3 — Connection pooling**
- *As an Operator, many concurrent users share DB connections efficiently.*
  - Slices: pool config; sane min/max; health under load.

**R4 — Multi-tenant scoping** *(overlaps Q4)*
- *As an Operator, every row is attributable to an owner so tenants are isolated.*
  - Slices: owner/org columns; indexes; scoped queries everywhere.

### Epic S — Bring-your-own-key (per-user Groq keys) · Wave H2 · **centerpiece**

**S1 — Per-user key storage (secure)**
- *As an Operator, each user's Groq key is stored encrypted at rest, server-side only.*
  - AC: keys are encrypted in the DB (not plaintext); never returned to the browser.
  - Slices: encrypted key column keyed by `uid`; encryption at rest (§7); read only at call time.

**S2 — Key entry UI (write-only)**
- *As a Learner, I paste my Groq key in Settings and only ever see "•••• set / replace" afterward.*
  - AC: the key is never rendered back into the page after saving.
  - Slices: settings key field; "replace" flow; write-only display.

**S3 — Per-session client construction**
- *As a Developer, the `LLMClient` for a session is built with that session's user's key.*
  - AC: `SessionManager` resolves the caller's key and constructs a `GroqClient` with it per request/session.
  - Slices: per-user key resolver; thread key into client construction; cache carefully (never across users).

**S4 — Save-time validation**
- *As a Learner, I find out at save time if my key is wrong, calmly in Settings.*
  - Slices: one tiny test call on save; clear pass/fail.

**S5 — Graceful key-failure handling**
- *As a Learner, if my key is missing/exhausted/invalid mid-session, I get a clear message, not a crash.*
  - AC: rate-limit / auth / missing-key errors surface as a friendly chat notice ("your Groq key is rate-limited — wait a minute or check Settings"), never a stack trace or silent hang.
  - Slices: catch provider errors in the LLM path; map to user-facing messages; a "no key set" gate before starting a session.

**S6 — Get-your-key guidance**
- *As a Learner (even a nervous one), a link and short steps to get a free Groq key sit right next to the field.*
  - Slices: inline guidance; link to `console.groq.com/keys`.

### Epic T — Hosting & operations (Railway) · Waves H0 / H3 / H4

**T1 — Containerization** — Dockerfile; runs `uvicorn`. *(H0)*
**T2 — Config & secrets** — env vars in Railway; no secrets in code. *(H0)*
**T3 — Deploy & HTTPS** — Railway service + Postgres plugin; HTTPS by default. *(H0)*
**T4 — Health & monitoring** — `/health` (exists); logs; is-Groq-erroring / queue-depth / DB-pool metrics. *(H3)*
**T5 — Backups** — automated Postgres backups; a tested restore. *(H4)*

### Epic U — Scale & safety hardening · Wave H3

**U1 — LLM request queue with backpressure**
- *As a Learner, during a busy moment my persona still replies (queued) rather than erroring.*
  - AC: bursts are smoothed; users see "typing…" not failures.
  - Slices: a job queue in front of the LLM calls (the `run_in_threadpool` seam); worker(s); backpressure.

**U2 — Per-user quotas & rate limits**
- *As an Operator, one runaway user or script can't degrade the service for others.*
  - Slices: per-user request/token meter; quota enforcement; friendly limit messages.

**U3 — Workers & pooling** — multiple uvicorn workers; DB pool tuning (with R3). 
**U4 — Abuse protection** — protect the *platform* (auth required, rate caps); note that with BYOK the *LLM cost* is the student's, so abuse here is about your compute/DB, not your inference bill.
**U5 — Load testing** — a script that simulates target concurrency; find the real ceiling.
**U6 — Usage visibility** — per-user usage (their key) + your platform costs (compute/DB) surfaced.

> **Reality check for U:** real peak concurrency is likely far below headcount —
> students spread across time zones, work at different paces, and spend long
> stretches coding locally (not hitting the server). Measure it; a "200-person
> cohort" may be "30–50 concurrent LLM requests." Build the queue regardless; size
> the rest to the measured peak.

### Epic V — Data protection & privacy · Waves H2 / H4

**V1 — Encryption at rest** *(lands with S1 in H2 — keys can't be stored plaintext even briefly)*
- *As an Operator, a DB leak exposes encrypted key blobs, not plaintext keys.*
  - Slices: encrypt the key column; manage the encryption key as a secret; consider encrypting transcripts.

**V2 — Retention & deletion** *(H4)*
- *As a Learner, I can have my data deleted.*
  - Slices: delete-user flow (sessions, transcripts, key); a retention policy.

**V3 — Privacy posture** *(H4)*
- *As an Operator, I have a defensible privacy stance for worldwide students.*
  - Slices: privacy note; data-location awareness; consent at signup.

**V4 — Incident readiness** *(H4)*
- *As an Operator, I have a documented response if keys or data leak.*
  - Slices: a short runbook (rotate encryption key, notify, revoke).

---

## 7. Security requirements for per-user keys (mandatory)

These are not optional. A UI that collects API keys is precisely where cutting
corners becomes a disclosable incident.

1. **Write-only display.** After saving, never render the key back — show
   "•••• set" + a "replace" button. Displaying it leaks via screenshots,
   history, and screen-shares.
2. **Encrypted at rest, server-side only.** Store encrypted, never plaintext.
   The browser posts it once; after that it moves only server-side (DB → LLM
   call). It is never sent back to any client or put in browser storage.
3. **Graceful failure is a normal path, not an edge case.** A student's own free
   key *will* be missing/wrong/rate-limited sometimes. Catch and explain it
   clearly; never crash or hang.
4. **Validate on save,** not on first use — so problems surface calmly in
   Settings, not mid-session with a client watching.

---

## 8. Cross-cutting non-functional requirements

- **Security:** all traffic over HTTPS; auth on every non-public route; keys and
  secrets encrypted; least-privilege DB access.
- **Privacy:** worldwide students imply GDPR-style expectations — consent,
  deletion, data-location awareness.
- **Reliability:** a down server strands a live cohort — health checks, backups,
  and (at scale) monitoring so you find issues before students do.
- **Cost:** with BYOK the *inference* cost is the student's; *your* costs are
  Railway compute + Postgres — modest and predictable, but a number to set, not
  discover.
- **Operability:** hosting means you are running a *service*, not a tool — an
  ongoing responsibility (uptime, a cost meter that runs whether or not anyone's
  active, someone hitting a problem at 3am your time). Treat the hosted build as a
  deliberate project, not a flag-flip.

## 9. Definition of Done (per story)

1. Behind the right port/seam; core domain unchanged.
2. Tests added (deterministic where possible; auth/DB/provider behind fakes).
3. Security requirements met where the story touches keys or auth.
4. Deployable — works on Railway, not just locally.
5. No regression to the local/LAN experience.

## 10. Explicitly out of scope (deferred)

- **Version B "server-run containers / code-server"** — running learner
  workspaces on the server. The `Environment` port is the seam if it's ever
  needed; deferred in favour of the patch-submission flow that already works.
- **Server-provided inference key / paid pooled key** — superseded by BYOK.
- **Auto-scaling / multi-region** — not needed at cohort scale; revisit only with
  measured evidence.
- **Grader calibration** — orthogonal to hosting; tracked separately.

## 11. Key decisions & their honest trade-offs

| Decision | Why | Trade-off accepted |
|---|---|---|
| Postgres over Firestore | Adapters are already SQL; awkward queries are native in Postgres | Firestore's managed-NoSQL scaling not used; fine at this size |
| Firebase Auth (not self-built) | Removes the scariest hosting chore | A vendor dependency for identity |
| Groq **per-user keys** (not a server key or pooled free keys) | Legitimate (each key is the user's own), free, scales with the cohort, no ban risk, no single point of failure | Onboarding friction (each student gets a key); a student can hit *their own* daily cap — but transparently theirs |
| Railway | Runs `uvicorn` as-is; managed Postgres alongside | A hosting vendor dependency |
| Build local-first, host later | Scale into measured evidence; avoid over-building | Remote students wait for the hosted build — acceptable, they're the reason to build it |

## 12. Recommended sequencing

1. **Keep local/LAN exactly as-is** for the in-room cohort.
2. **H0 → H1 → H2** to reach the hosted MVP (deployable → safe → usable by remote
   students on their own keys). This is the smallest thing that serves worldwide
   students legitimately.
3. **Run real remote cohorts.** Measure peak concurrency and cost.
4. **H3 → H4** only as the measured load and your operational comfort justify —
   scaling into evidence, not ahead of it.
