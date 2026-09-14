# Auth Plan — Firebase Email, three roles, three dashboards

> **Status: planning only. Nothing here is built.** This is the implementation
> plan for replacing the shared instructor password with real accounts, without
> breaking the local/LAN simulator that already works.

This plan is the detailed expansion of **Epic Q** in `DEPLOYMENT-PLAN.md`. That
document covers hosted identity at a high level. This one is the build order:
ports, adapters, dashboards, Firebase console work, and the tests that keep
personas, director, grading, tickets, interview assessment, and replay intact.

---

## 0. Why this is a bounded project, not a rewrite

Auth today is one function in the FastAPI adapter:

```python
# sim/adapters/web/app.py
def _instr_ok(token: str) -> bool:
    return bool(app.state.instructor_password) and token == app.state.instructor_password
```

The frontend stores the raw password and sends it as `X-Instructor-Token` on
every instructor API call (`instructor.html` → `hdr()`). Default secret:
`$T0mV13w` (`Config.instructor_password` / `INSTRUCTOR_PASSWORD`). Documented as
a light gate, not real security (`GET_STARTED_INSTRUCTOR.md`, `docs/INSTRUCTOR.md`).

Everything else is **unguarded**. Knowledge of `session_id` (a ~7-char client
hash in the URL, generated in `shell.js` and `instructor.html`) is enough to
read transcripts, submissions, grade, chat over WebSocket, provision sandboxes,
and move tickets.

The hexagonal layout already has the seam: **core stays framework-free**
(`test_smk02_core_stays_pure`). Firebase, JWT verification, and HTTP headers
live in adapters. Composition happens in `sim/app/composition_root.py`.

---

## 1. Target (what “done” looks like)

Three roles, email/password via Firebase Auth, three dashboards, ownership on
every session.

| Role | Who | What they can do |
|---|---|---|
| **Challenger** | Student / candidate | Sign in, see *their* assigned sessions, open the workstation, submit, self-grade, see their own results. Cannot open instructor/admin surfaces or other people’s sessions. |
| **Instructor** | Teacher | Sign in, create/assign sessions, replay, grade (with tickets toggle), export markdown audits, manage *their* settings and starter URLs. Sees only sessions they (or their org) own. |
| **Admin** | Operator | Full CRUD on **every** persisted entity and config surface: users, roles, sessions, transcripts, mail, tickets, submissions, settings, scenario starter URLs, sandbox teardown, grades/exports. Impersonation is *not* in v1 (see §11). |

**Email auth only** for v1 (Firebase Email/Password). No Google, no magic link
until a later slice. Password reset and email verification are in-wave, not
stretch.

**Local/LAN is preserved.** Default `AUTH_MODE=password` keeps today’s shared
password so `test_smk14` and the classroom flow keep passing. Firebase is
opt-in (`AUTH_MODE=firebase`). Hosted deploys must set Firebase and refuse to
boot on the default password.

---

## 2. Current surfaces (so the plan maps 1:1 onto code)

### Pages (two today → five when this ships)

| Route | File | Today |
|---|---|---|
| `GET /` | `sim/adapters/web/static/index.html` + `shell.js` + `apps/*.js` | Challenger workstation. No login. Session from `#s-xxxxx`. |
| `GET /instructor` | `sim/adapters/web/static/instructor.html` | Login overlay → password. New session, Sessions, Replay, Grade, Export, Settings. |

**Add:** `/login`, `/challenger`, `/admin`. Rewrite `/instructor` to use Firebase
instead of the password overlay.

### Instructor-gated APIs (`X-Instructor-Token`)

`GET/POST /api/instructor/settings`, `POST .../session/{id}/level`,
`POST .../session/{id}/scenario`, `POST .../scenario/{key}/starter-url`,
`GET /api/instructor/sessions`, `GET /api/instructor/session/{sid}`,
`GET /api/instructor/session/{sid}/export.md`.

`POST /api/instructor/auth` is unguarded (it *is* the password check).

### Public (anyone with a `session_id`) — must become role-scoped in Firebase mode

All `/api/session/{id}/*` (start, end, transcript, grade, diagram, submit,
submissions, environment, files, tickets, mail), `GET /api/scenarios`,
`GET /api/levels`, WebSocket `/ws/{session_id}`.

**Known hole:** instructor replay Grade calls `POST /api/session/{sid}/grade`
with **no** instructor header (`doGrade()` in `instructor.html`). Chat.js does
the same for self-grade. Auth must keep both, with different roles.

### Persistence (no users, no owners)

Single SQLite file (`SIM_DB_PATH`). Stores keyed only by `session_id`:

| Store | Adapter | Tables |
|---|---|---|
| Transcript | `sqlite_repo.py` | `messages` |
| Unlock | `sqlite_state.py` | `unlock_state` |
| Mail | `sqlite_mail.py` | `mail_threads` |
| Tickets | `sqlite_tickets.py` | `tickets` |
| Settings | `sqlite_settings.py` | `instructor_settings` (singleton `id=1`), `session_settings`, `scenario_config` |
| Submissions | `sqlite_submissions.py` | `submissions` (full patch content) |

Session list = `GROUP BY session_id` on `messages`. A pre-created link with no
chat does **not** appear in Sessions. Auth work includes a real **session
registry** so assigned-but-unstarted sessions exist.

No `users` table. Sender `"tester"` is the only learner identity.

---

## 3. Architecture (SOLID, modular, DIP)

```
sim/core/ports/identity.py          Principal, Role, IdentityVerifier (Protocol)
sim/core/ports/users.py             UserRecord, UserDirectory (Protocol)
sim/core/ports/session_registry.py  SessionRecord, SessionRegistry (Protocol)
sim/core/access/policy.py           pure: can_read_session, can_grade, can_admin_crud
                                    (no Firebase, no FastAPI — SMK-02 safe)

sim/adapters/auth/firebase_verifier.py   verify ID token → Principal
sim/adapters/auth/fake_verifier.py       tests / AUTH_MODE=fake
sim/adapters/auth/password_gate.py       today's shared password as a Principal
sim/adapters/web/deps.py                 FastAPI Depends(require_principal), role guards
sim/adapters/web/app.py                  thin: call deps, then existing services
sim/adapters/persistence/sqlite_users.py
sim/adapters/persistence/sqlite_sessions.py   registry (owner, assignee, scenario, level)

sim/adapters/web/static/
  auth.js                 shared: sign-in, token header, sign-out
  login.html
  challenger.html         challenger dashboard
  instructor.html         rewrite (keep replay/grade/export)
  admin.html              admin dashboard
  index.html / shell.js   workstation; require token in firebase mode
```

**Rules**

1. **SRP** — verify tokens ≠ decide roles ≠ own sessions ≠ render dashboards.
2. **OCP** — new verifier (`Fake` / `Firebase` / `Password`) without changing
   `SessionService`.
3. **LSP** — every verifier returns the same `Principal`.
4. **ISP** — `IdentityVerifier.verify(token) → Principal`; directory and registry
   are separate ports.
5. **DIP** — `create_web_app` depends on the ports; `composition_root` wires
   Firebase or Fake from `Config.auth_mode`.
6. **Core purity** — `firebase_admin`, FastAPI, `google.oauth2` never appear
   under `sim/core/`. Extend `test_smk02` `FORBIDDEN_TOP` with `firebase_admin`.

**`Principal`** (core value object): `uid`, `email`, `role` (`challenger` |
`instructor` | `admin`), `disabled`. Role is taken from a **verified** custom
claim *or* the local `users` row (local row wins if they disagree — admin can
revoke without waiting for token refresh). Never trust a client-sent `role`.

**Password mode Principal:** `uid="local-instructor"`, `role="instructor"` when
the shared password matches. Challenger APIs stay open (today’s LAN classroom).
Admin dashboard is hidden.

---

## 4. Config (programmatic)

Add to `sim/app/config.py` (defaults keep current tests green):

| Field | Env | Default | Meaning |
|---|---|---|---|
| `auth_mode` | `AUTH_MODE` | `password` | `password` \| `firebase` \| `fake` |
| `instructor_password` | `INSTRUCTOR_PASSWORD` | `$T0mV13w` | Only used when `auth_mode=password` |
| `firebase_project_id` | `FIREBASE_PROJECT_ID` | `""` | Required if `firebase` |
| `firebase_credentials` | `GOOGLE_APPLICATION_CREDENTIALS` or `FIREBASE_CREDENTIALS_JSON` | `""` | Service account for Admin SDK |
| `firebase_web_api_key` | `FIREBASE_WEB_API_KEY` | `""` | Client SDK (email sign-in) |
| `firebase_auth_domain` | `FIREBASE_AUTH_DOMAIN` | `""` | `{project}.firebaseapp.com` |
| `bootstrap_admin_email` | `AUTH_BOOTSTRAP_ADMIN_EMAIL` | `""` | First admin if users table is empty |

Boot rules:

- `AUTH_MODE=firebase` and missing project/credentials → **refuse to start**.
- `AUTH_MODE=firebase` and `INSTRUCTOR_PASSWORD` still the default → log a
  warning; do not use the password path.
- `AUTH_MODE=fake` is test-only (Fake verifier, header `X-Test-Uid`).

Expose a public `GET /api/auth/config` with **only** what the browser needs
(`auth_mode`, web api key, auth domain, project id). Never credentials JSON.

---

## 5. Human steps (Firebase console — do these before Wave A2 ships)

These are operator actions. They are part of the backlog, not “someone will
remember.”

### H-1. Create the project
1. [Firebase console](https://console.firebase.google.com/) → Add project.
2. Disable Google Analytics unless you already want it (not required for auth).
3. Note **Project ID**.

### H-2. Enable Email/Password
1. Build → Authentication → Sign-in method.
2. Enable **Email/Password** (not Email link).
3. Leave Google/anonymous **off** for v1.

### H-3. Register the web app
1. Project settings → Add app → Web.
2. Copy **API key**, **Auth domain**, **Project ID** into env
   (`FIREBASE_WEB_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`).
3. Add authorized domains: `localhost`, classroom LAN host if used, later the
   Railway/custom domain.

### H-4. Service account (server verification)
1. Project settings → Service accounts → Generate new private key.
2. Save outside the repo. Point `GOOGLE_APPLICATION_CREDENTIALS` at the file,
   *or* paste JSON into `FIREBASE_CREDENTIALS_JSON` on the host.
3. Never commit the JSON. Add `*-firebase-adminsdk-*.json` to `.gitignore`.

### H-5. First admin
Pick one:

- **A (recommended):** create the user in Authentication → Add user (email +
  password). Set `AUTH_BOOTSTRAP_ADMIN_EMAIL` to that email. First server boot
  with an empty `users` table writes `role=admin` for that email.
- **B:** Firebase CLI / Admin SDK one-liner to set custom claim
  `{ "role": "admin" }` on that uid, then sync into `users` on first login.

Until an admin exists, **nobody** can promote instructors. Document this in
`GET_STARTED_INSTRUCTOR.md`.

### H-6. Email templates
1. Authentication → Templates: action URL for password reset + email
   verification must match authorised domains.
2. Send a test reset to the bootstrap admin before inviting challengers.

### H-7. Classroom vs hosted
- **LAN class this week:** keep `AUTH_MODE=password`. Do not enable Firebase
  until you want accounts.
- **Hosted:** `AUTH_MODE=firebase` + H-1…H-6 **before** binding to the public
  internet (`DEPLOYMENT-PLAN.md` principle: auth before exposure).

---

## 6. Waves (delivery increments)

Each wave is independently shippable. Exit criterion is tests + a manual path.
Default `AUTH_MODE=password` until Wave A2; existing smoke/regression must stay
green at every wave.

| Wave | Name | Goal | Exit criterion |
|---|---|---|---|
| **A0** | Seams | Ports, Fake verifier, policy functions, `AUTH_MODE`, SMK-02 extended. Password path unchanged. | Full current suite green. New unit tests for policy. App still uses `_instr_ok` when `password`. |
| **A1** | Session registry + users table | SQLite `users` + `sessions` registry; password mode still works; instructor “New session” writes a registry row (optional owner `local-instructor`). | Pre-created sessions appear in the list. LIB/SYS/IV tests still pass. |
| **A2** | Firebase email | Verify ID tokens; `/login`; shared `auth.js`; instructor dashboard signs in with email. Password mode still default. | Instructor can sign in with a Firebase email when `AUTH_MODE=firebase`; token on instructor APIs; Fake path covers CI. |
| **A3** | Roles | Challenger / instructor / admin claims + local `users` row; guards on routes. Bootstrap admin. | Challenger 403s on `/api/instructor/*`. Admin reaches `/api/admin/*`. |
| **A4** | Dashboards | Challenger dashboard, instructor rewrite, admin dashboard shell. Workstation requires login in firebase mode. | Three pages, role redirect from `/login`. |
| **A5** | Ownership | Sessions owned by instructor, assigned to challenger; all session APIs + WS scoped. Grade split: self vs instructor. | Cross-user session access returns 403. SMK-03 websocket still works in password + fake modes. |
| **A6** | Admin CRUD | Full CRUD APIs + admin UI for every store listed in §8. | Admin can list/get/update/delete users, sessions, settings, starter URLs, and session-scoped records. |
| **A7** | Harden | Email verification, password reset UI, disable user, audit log of admin writes, retire password in firebase mode. | Firebase mode has no `X-Instructor-Token` password path. Password mode still exists for LAN. |

**Do not skip A0.** Wiring Firebase into `app.py` without a port is how SMK-02
and the FakeLLM suite rot.

---

## 7. Epics → Features → Stories → Slices

Roles in stories: **Challenger**, **Instructor**, **Admin**, **Developer**,
**Operator**.

---

### Epic A — Identity ports & dual-mode config · Wave A0

**A1 — Principal & verifier port**
- *As a Developer, I verify identity behind a port so core never imports Firebase.*
  - AC: `IdentityVerifier.verify(token: str) -> Principal` in
    `sim/core/ports/identity.py`. Fake implementation in adapters. `test_smk02`
    still passes; `FORBIDDEN_TOP` includes `firebase_admin`.
  - Slices: `Principal` dataclass + `Role` enum/literals; Protocol; Fake that
    maps `test:<uid>:<role>` tokens; unit tests `tests/unit/test_identity_port.py`.

**A2 — Access policy (pure)**
- *As a Developer, authorization is a function of Principal + resource, not of
  FastAPI.*
  - AC: `sim/core/access/policy.py` answers `can_access_session`, `can_mutate_session`,
    `can_grade_as_instructor`, `can_admin`. No I/O.
  - Slices: truth table tests (challenger own/other, instructor own/other, admin
    all, disabled user none).

**A3 — Config dual-mode**
- *As an Operator, I choose password, firebase, or fake without code edits.*
  - AC: `Config.auth_mode`; `composition_root` wires the matching verifier;
    default `password` preserves SMK-14.
  - Slices: env parse; boot-fail if firebase misconfigured; `GET /api/auth/config`
    public payload; smoke `test_smk20_auth_mode_password_default`.

---

### Epic B — User directory & session registry · Wave A1

**B1 — Users table**
- *As an Admin, accounts exist locally so I can assign roles even if a Firebase
  claim is stale.*
  - AC: `UserDirectory` port + SQLite adapter: `uid`, `email`, `role`,
    `disabled`, `created_at`, `last_login`. Unique email.
  - Slices: schema/migration (`CREATE TABLE IF NOT EXISTS` like existing stores);
    memory adapter for unit tests; `tests/unit/test_user_directory.py`.

**B2 — Session registry**
- *As an Instructor, a session exists as soon as I create the link, not only
  after the first chat message.*
  - AC: `SessionRegistry` with `id`, `owner_uid`, `assignee_uid`, `scenario_key`,
    `level`, `created_at`, `status` (`assigned` \| `active` \| `ended`).
    `GET /api/instructor/sessions` reads the registry, not `GROUP BY messages`.
  - Slices: SQLite + memory adapters; backfill: existing `messages.session_id`
    rows become registry rows (`owner_uid=local-instructor`) on first boot;
    update `instructor.html` New session to `POST /api/instructor/sessions`
    (server allocates id — stop client `Math.random`).
  - Regression: `test_smk16`, `test_sys04`, `test_iv05` still assign scenario
    via the new create endpoint *or* keep the old POST scenario/level as
    aliases that also upsert the registry.

**B3 — Server-issued session ids**
- *As a Developer, session ids are allocated by the server so the client cannot
  mint foreign ids.*
  - AC: `POST /api/instructor/sessions` returns `{session_id, url}`. Ids remain
    URL-safe (e.g. `s-` + uuid4 hex slice) for the workstation hash.
  - Slices: replace random in `instructor.html`; password mode: owner =
    `local-instructor`.

---

### Epic C — Firebase email sign-in · Wave A2

**C1 — Server token verification**
- *As a Developer, I verify a Firebase ID token in one place so no endpoint
  trusts the client for `uid`.*
  - AC: `FirebaseVerifier` uses Admin SDK `verify_id_token`. Invalid/expired →
    401. `uid` + email from token; role from `users` row (create on first login
    as `challenger` unless bootstrap admin email).
  - Slices: adapter; FastAPI `Depends(require_principal)`; replace `_instr_ok`
    **only when** `auth_mode=firebase`; password mode keeps `_instr_ok`.
  - Tests: Fake verifier in CI (no network). Optional `@pytest.mark.firebase`
    live test, excluded like `eval`.

**C2 — Login page**
- *As a Challenger or Instructor, I sign in with email and password.*
  - AC: `/login` uses Firebase JS SDK `signInWithEmailAndPassword` /
    `createUserWithEmailAndPassword` (sign-up can be instructor-invite-only —
    see C4). Stores ID token; `Authorization: Bearer <idToken>` on API calls.
    Sign-out clears token and redirects to `/login`.
  - Slices: `login.html` + `auth.js`; token refresh (`onIdTokenChanged`);
    hide password overlay on instructor when firebase mode.

**C3 — Instructor dashboard uses auth**
- *As an Instructor, the dashboard I already use asks for my email, not a
  classroom password.*
  - AC: `instructor.html` `login()` / `hdr()` use Bearer token when
    `auth_mode=firebase`; password overlay remains when `password`. Settings,
    New session, Sessions, Replay, Export all send the token. Grade sends the
    token too (fixes the unguarded `doGrade()` hole in firebase mode).
  - Slices: branch on `/api/auth/config`; keep SMK-14 against password mode.

**C4 — Sign-up policy**
- *As an Operator, random people cannot self-promote to instructor.*
  - AC: public sign-up creates **challenger** only. Instructors are created by
    Admin (invite: Admin creates Firebase user + `users.role=instructor`, sends
    password-reset email). Document the invite path.
  - Slices: `POST /api/auth/register` (optional; or client SDK sign-up +
    server first-login insert as challenger); reject role in the request body.

**C5 — Password reset & verification (UI)**
- *As a Challenger, I can reset a forgotten password and verify my email.*
  - AC: login page links; Firebase `sendPasswordResetEmail` /
    `sendEmailVerification`. Server may require `email_verified` for
    instructor/admin (configurable; challenger can be lax for classroom speed).
  - Slices: UI copy; H-6 templates; smoke against Fake (no send).

---

### Epic D — Roles & route guards · Wave A3

**D1 — Role model**
- *As an Operator, challenger, instructor, and admin have different powers.*
  - AC: role stored on `users` and optionally mirrored as Firebase custom claim
    (Admin SDK `set_custom_user_claims`) so the token itself cannot grant
    admin without the DB row.
  - Slices: `require_role("instructor")` allows instructor **or** admin;
    `require_role("admin")` admin only; challenger default.

**D2 — Bootstrap admin**
- *As an Operator, the first account with `AUTH_BOOTSTRAP_ADMIN_EMAIL` becomes
  admin so I am not locked out.*
  - AC: empty directory + matching email → `role=admin` once. Later logins do
    not demote. Test with Fake.
  - Human: H-5.

**D3 — Guard instructor APIs**
- *As a Challenger, I cannot list all sessions or change settings.*
  - AC: `/api/instructor/*` requires instructor|admin. 403 not 401 when signed
    in as challenger. Password mode: unchanged shared-password gate.
  - Slices: one dependency used by every instructor route; regression tests
    `test_reg_auth_challenger_blocked_from_instructor`.

**D4 — `/me`**
- *As any signed-in user, I see my email and role so the UI can route me.*
  - AC: `GET /api/auth/me` → `{uid, email, role, disabled}`. Dashboards redirect
    on role.

---

### Epic E — Three dashboards · Wave A4

Visual language: keep the existing dark instructor theme (`instructor.html`
CSS variables) so the product still feels like one app.

**E1 — Shared shell**
- *As a Developer, login, token, and nav are one module.*
  - Slices: `auth.js` (`getToken`, `api`, `signOut`, `requireRole`); role-based
    header (Challenger / Instructor / Admin links the user is allowed to see).

**E2 — Challenger dashboard (`/challenger`)**
- *As a Challenger, I see the challenges assigned to me and open one.*
  - AC: list of *my* sessions (scenario title, track badge, difficulty, level,
    status). **Open** → `/#<session_id>` workstation. Empty state: “Your
    instructor has not assigned a session yet.” No New-session, no all-sessions,
    no settings for the classroom password, no admin.
  - Slices: `challenger.html`; `GET /api/me/sessions`; deep link still works if
    assigned; 403 if opening someone else’s id.

**E3 — Instructor dashboard rewrite (`/instructor`)**
- *As an Instructor, I keep New session, Sessions, Replay, Grade, Export,
  Settings — now behind my account.*
  - AC: parity with today’s views (onboarding default level, scenario optgroups
    Product / Systems / Interview, match warning, copyable trainee link,
    tickets extra-credit toggle, markdown export). New: **assign to a
    challenger** (email or uid picker from the org’s challengers). Link can
    still be copied for LAN, but firebase mode prefers assignment so the
    workstation checks `assignee_uid`.
  - Slices: replace password overlay; `hdr()` Bearer; New session calls
    registry POST; Sessions from registry; keep replay JS (timeline, chips,
    scrub) — do not rewrite replay in this epic.

**E4 — Admin dashboard (`/admin`)**
- *As an Admin, I have a home that can reach every CRUD surface.*
  - AC: nav: Users, Sessions (all instructors), Settings (global), Scenarios
    (starter URLs + enable/disable if we add a flag), Audit (A7). Each nav
    item is a later feature in Epic G; A4 ships the shell + Users list +
    “open session as replay” using existing instructor replay APIs (admin
    is allowed).
  - Slices: `admin.html`; reuse replay component or iframe `/instructor`
    replay with admin token (prefer reuse, don’t duplicate timeline).

**E5 — Workstation gate**
- *As a Challenger, the desktop at `/` requires sign-in when Firebase is on.*
  - AC: `shell.js` fetches `/api/auth/config`; if firebase, redirect to
    `/login` then back. Pass Bearer to REST; WebSocket auth per F3.
  - Password mode: no redirect (LAN class unchanged).
  - Slices: `shell.js` branch; subtitle can show signed-in email.

**E6 — Role home**
- *As a user, `/login` success sends me to the right dashboard.*
  - Challenger → `/challenger`; instructor → `/instructor`; admin → `/admin`
    (admin can still open the other two).

---

### Epic F — Ownership & session APIs · Wave A5

**F1 — Scope every session read/write**
- *As a Challenger, my transcript is private. As an Instructor, I only see
  mine. As an Admin, I see all.*
  - AC: helper `assert_session_access(principal, session_id, mutate=False)`
    used by every `/api/session/{id}/*` handler and the websocket. Policy from
    Epic A. 404 vs 403: use **403** when authenticated but not allowed (don’t
    leak existence if we can cheaply 403 uniformly; acceptable to 404 to
    avoid enumeration — pick 404 for challenger, 403 for instructor hitting
    another instructor’s session). Document the choice in tests.
  - Slices: wrap existing routes; do **not** change `SessionService` signatures
    unless a `principal` is needed for “tester” labelling (optional: store
    `uid` on tester messages later).

**F2 — Grade endpoint policy**
- *As a Challenger, I can grade my run. As an Instructor, I can grade my
  cohort. As an Admin, I can grade any.*
  - AC: same `POST /api/session/{id}/grade`; policy allows assignee
    (self-grade) or owner instructor or admin. `include_tickets` unchanged.
  - Slices: fix instructor `doGrade()` to send auth; add
    `test_reg_auth_grade_forbidden_cross_user`.

**F3 — WebSocket auth**
- *As a Challenger, chat cannot be hijacked with only a session id.*
  - AC: `/ws/{session_id}?token=<idToken>` (browsers cannot set WS headers
    reliably) **or** cookie set at login (`SameSite=Lax`, `HttpOnly` session
    cookie minted after verify — prefer cookie if we add a server session;
    v1 token query is acceptable if tokens are short-lived and not logged).
    Reject if principal cannot access the session.
  - Slices: Starlette WS; Fake token in tests; update `chat.js` `connect()`.
    **Password mode:** keep unauthenticated WS (SMK-03).

**F4 — Scenarios/levels listing**
- *As a Challenger, I can see the scenario *of my session* but not necessarily
  the full library + starter URLs.*
  - AC: `GET /api/scenarios` instructor|admin; challenger gets scenario
    metadata via existing `/api/session/{id}/scenario` only. Hidden needs never
    in any of these payloads (already true — `hidden_need` is not in
    `_scenario_info`).
  - Slices: gate `/api/scenarios`; keep instructor New-session working.

**F5 — Create + assign**
- *As an Instructor, I create a session for a named challenger so they see it
  on their dashboard.*
  - AC: POST body `{scenario, level, assignee_email?}`. If email omitted
    (LAN), assignee empty until first challenger with the link claims it
    (`POST /api/session/{id}/claim` once). Firebase mode: prefer required
    assignee.
  - Slices: claim endpoint (only if unassigned); prevent steal if already
    assigned.

---

### Epic G — Admin full CRUD · Wave A6

Admin APIs live under `/api/admin/...` and require `role=admin`. Every resource
that exists in SQLite today is listed. “Full CRUD” means list/get/create/update/
delete unless a row is append-only (messages: delete session cascade; no
rewrite of history except delete).

**G1 — Users CRUD**
- *As an Admin, I create, list, update role, disable, and delete users.*
  - AC:
    - `GET /api/admin/users`
    - `POST /api/admin/users` `{email, role, send_reset: true}` → Admin SDK
      `create_user` + directory row
    - `PATCH /api/admin/users/{uid}` `{role, disabled}`
    - `DELETE /api/admin/users/{uid}` (Firebase disable + local row; hard
      delete optional flag)
  - Cannot delete the last admin.
  - Slices: UI table on `/admin` Users; Fake directory in tests (no Firebase
    network); `test_reg_auth_admin_users_crud`.

**G2 — Sessions CRUD**
- *As an Admin, I list every session, open replay, reassign owner/assignee,
  change scenario/level, end, and delete (cascade transcript, mail, tickets,
  submissions, unlock, sandbox).*
  - AC: `GET /api/admin/sessions`; `PATCH` owner/assignee/scenario/level/status;
    `DELETE` cascade. Replay uses existing instructor detail payload.
  - Slices: cascade teardown through existing `environment.teardown`; registry
    delete; tests that messages rows are gone.

**G3 — Transcript / mail / tickets / submissions / unlock**
- *As an Admin, I can read and delete these per session (and post a ticket or
  mail if needed for support).*
  - AC: nested routes
    `GET/DELETE /api/admin/sessions/{id}/messages`
    `GET/DELETE /api/admin/sessions/{id}/mail`
    `GET/POST/PATCH/DELETE /api/admin/sessions/{id}/tickets/{tid}`
    `GET/DELETE /api/admin/sessions/{id}/submissions`
    `POST /api/admin/sessions/{id}/unlock/reset`
  - Slices: wrap existing stores; do not put CRUD in `sim/core/session_service.py`
    beyond small explicit admin methods on adapters.

**G4 — Settings CRUD**
- *As an Admin, global instructor settings and per-session settings are editable.*
  - AC: `GET/PUT /api/admin/settings` (onboarded, default_level — today a
    singleton; later per-instructor). `PUT /api/admin/sessions/{id}/settings`.
  - Note: singleton `instructor_settings id=1` is a known limitation; G4 may
    add `owner_uid` on settings as a slice if multiple instructors share a DB.

**G5 — Scenario config CRUD**
- *As an Admin, I set starter GitHub URLs and (optional) disable a scenario
  without deleting YAML from disk.*
  - AC: `GET/PUT /api/admin/scenarios/{key}` `{starter_url, enabled}`. YAML
    files remain the source of personas/rubrics (Open/Closed). **Do not**
    expose `hidden_need` on challenger APIs. Admin GET of a scenario may
    include it for debugging (slice, behind admin only).
  - Slices: `enabled` column on `scenario_config`; registry skips disabled
    for instructor New-session.

**G6 — Environment / files**
- *As an Admin, I can provision, list files, and teardown any sandbox.*
  - AC: admin aliases of existing environment/files routes, or the same
    routes with admin principal. Teardown on session delete (G2).

**G7 — Grade & export**
- *As an Admin, I can grade and export any session (including tickets extra
  credit).*
  - AC: existing grade + export.md endpoints allowed for admin; admin UI
    buttons. No new grader.

**G8 — Auth config (read)**
- *As an Admin, I can see auth mode and bootstrap email (not secrets).*
  - AC: `GET /api/admin/auth/status` `{auth_mode, firebase_project_id,
    users_count, bootstrap_configured}`.

**G9 — Admin UI completeness**
- *As an Admin, every G1–G8 endpoint has a screen or a confirmed reuse of
  instructor replay.*
  - AC: Users, All sessions, Session detail (replay + danger-zone delete),
    Settings, Scenarios. Not pretty; functional. Same CSS family.

---

### Epic H — Harden & retire password-in-firebase · Wave A7

**H1 — Disable & revoke**
- *As an Admin, a disabled user gets 403 on the next request even if their
  token is still valid.*
  - AC: `users.disabled` checked on every verify. Optional: Admin SDK
    `revoke_refresh_tokens`.

**H2 — Admin write audit**
- *As an Operator, I can see who deleted a session or changed a role.*
  - AC: `admin_audit` table: `ts, actor_uid, action, resource, payload`.
    `GET /api/admin/audit`. No PII in passwords. Slice: append-only.

**H3 — Firebase mode drops password header**
- *As an Operator, hosted Firebase mode does not accept `X-Instructor-Token:
  $T0mV13w`.*
  - AC: if `auth_mode=firebase`, `_instr_ok` is never consulted. Tests cover
    both modes.

**H4 — Docs**
- *As an Instructor, I know which mode I’m in.*
  - AC: update `GET_STARTED_INSTRUCTOR.md`, `GET_STARTED_STUDENT.md`,
    `docs/CLASSROOM.md`, `docs/INSTRUCTOR.md`. Point at this file and H-1…H-7.
    `DEPLOYMENT-PLAN.md` Epic Q links here.

---

## 8. Admin CRUD inventory (nothing omitted)

| Resource | Create | Read | Update | Delete | Notes |
|---|---|---|---|---|---|
| Users | G1 | G1 | role, disabled | G1 | Last admin protected |
| Firebase user | via Admin SDK on G1 create | — | disable | disable | Server-side only |
| Sessions (registry) | Instructor + Admin | scoped | owner, assignee, scenario, level, status | cascade G2 | |
| Messages | via chat (not admin forge in v1) | G3 | — | cascade / G3 | Append-only |
| Mail threads | G3 optional | G3 | — | G3 | |
| Tickets | G3 | G3 | status/fields | G3 | |
| Submissions | learner submit | G3 (includes content) | — | G3 | Sensitive |
| Unlock state | — | G3 | reset | cascade | |
| Instructor settings | — | G4 | G4 | reset-onboarding | Singleton today |
| Session settings | on create | G4 | G4 | cascade | |
| Scenario starter URL | G5 | G5 | G5 | clear URL | |
| Scenario enabled flag | G5 | G5 | G5 | — | YAML stays on disk |
| Sandbox | provision | files list/read | — | teardown | |
| Grade | POST grade | last result not stored today — optional `grades` table slice | re-grade | — | LLM; Fake in tests |
| Export markdown | GET | — | — | — | |
| Audit log | auto | G H2 | — | — | Admin only |
| Auth status | — | G8 | — | — | No secrets |

**Explicitly not in v1:** editing `hidden_need` inside YAML from the UI;
impersonating a challenger (open their WS as them); forging tester chat as
admin (use replay + tickets instead).

---

## 9. Test plan (do not regress the product)

### 9.1 Invariants — must stay green every wave

Run `python -m pytest` (excludes `eval`) after **each** slice that touches
`app.py`, `composition_root.py`, `config.py`, or static dashboards.

| Suite | Why it exists |
|---|---|
| `tests/smoke/test_smoke.py` SMK-01..19 | Boot, core purity, WS, instructor gate, levels, multi-scenario, submissions |
| `tests/regression/test_sys_design.py` | Systems track submit → review |
| `tests/regression/test_interview.py` | Interview start, assessor, diagram, export, tickets toggle |
| `tests/regression/test_scenario_library.py` | Wellformed library, `session_start` triggers |
| `tests/regression/test_levels.py` | Pressure / posture |
| `tests/regression/test_tickets.py`, `test_mail.py`, `test_director_ticket.py` | Surfaces |
| `tests/regression/test_multiscenario.py` | Two scenarios concurrent |
| `test_smk02` | Core must not import Firebase/FastAPI |

Password mode (`AUTH_MODE` unset) **is** the default in these tests. Do not
flip the default to firebase in CI.

### 9.2 New unit tests (`tests/unit/`)

Deterministic, no TestClient required where possible:

- `test_identity_port.py` — Fake verifier, Principal
- `test_access_policy.py` — role × resource matrix
- `test_user_directory.py` — memory + sqlite
- `test_session_registry.py` — create, list by owner, list by assignee, backfill

### 9.3 New smoke (`test_smoke.py` or `tests/smoke/test_auth_smoke.py`)

| ID | Case |
|---|---|
| SMK-20 | Default auth_mode is password; SMK-14 still passes |
| SMK-21 | `AUTH_MODE=fake` + `X-Test-Uid` instructor can list sessions |
| SMK-22 | Fake challenger 403 on `/api/instructor/sessions` |
| SMK-23 | Fake admin 200 on `/api/admin/users` |
| SMK-24 | Core purity forbids `firebase_admin` |
| SMK-25 | `GET /api/auth/config` has no credentials JSON |
| SMK-26 | Firebase mode misconfig (missing project) fails boot or 503 health detail |

### 9.4 New regression (`tests/regression/test_auth.py`)

| ID | Case |
|---|---|
| AUTH-01 | Create session as instructor → appears for assignee challenger, not another challenger |
| AUTH-02 | Cross-tenant transcript 403/404 |
| AUTH-03 | Grade allowed for assignee + owner + admin, not a stranger |
| AUTH-04 | WS rejected without token in fake/firebase mode; password mode still SMK-03 |
| AUTH-05 | Interview export still 200 for owning instructor with Bearer; 401 without |
| AUTH-06 | Systems submit review still fires (director) when challenger is authenticated |
| AUTH-07 | Admin cascade delete removes messages + tickets |
| AUTH-08 | Challenger cannot PATCH user roles |
| AUTH-09 | Last admin cannot be deleted |
| AUTH-10 | Instructor dashboard API: settings + new session + replay detail with Fake token |
| AUTH-11 | `/api/scenarios` hidden from challenger; session scenario still works |
| AUTH-12 | Tickets extra-credit grade toggle still changes payload (`include_tickets`) |

### 9.5 Harnesses

| Harness | Purpose |
|---|---|
| **FakeVerifier** | CI identity. Header `Authorization: Bearer fake:<uid>:<role>` or `X-Test-Uid` + `X-Test-Role`. |
| **Password mode** | Default; existing `_app_with(..., instructor_password="$T0mV13w")` helpers stay. |
| **Firebase marker** | `@pytest.mark.firebase` — skipped unless `FIREBASE_TEST=1` and credentials present. One live verify + one rejected token. Same pattern as `eval`. Add marker in `pyproject.toml`. |
| **Playtest script** | `docs/PLAYTEST.md` addendum: three browsers / three emails — assign, play, replay, admin delete. Manual, not CI. |

### 9.6 What we will not do

- Do not call real Firebase in the default suite (cost, flakes, secrets).
- Do not put ID tokens in assertion logs.
- Do not weaken FakeLLM tests by requiring network.
- Do not skip SMK-02 “just this once” to import Firebase in core.

---

## 10. Suggested code slices (first PR = Wave A0)

Keep PRs small. Suggested first diff:

1. `sim/core/ports/identity.py` + `sim/core/access/policy.py`
2. `sim/adapters/auth/fake_verifier.py`
3. `Config.auth_mode`
4. `tests/unit/test_access_policy.py` + SMK-20 + SMK-24
5. **No** behaviour change in `app.py` yet except reading `auth_mode`

Second PR (A1): registry + users tables, instructor sessions list reads
registry with backfill, still password-gated.

Third PR (A2): Firebase adapter behind the port, `/login`, instructor
`hdr()` branch.

---

## 11. Out of scope (captured, not planned)

- Google / SSO / magic-link (Firebase can add them later; same verifier).
- Impersonate-as-challenger.
- Per-org tenancy beyond `owner_uid` (a later `org_id` column).
- Rewriting replay, chat, tickets, or mermaid.
- A third database. Hosted persistence is Firestore
  (`DEPLOYMENT-PLAN.md` Epic R). Auth adapters stay store-agnostic.
- BYOK Groq keys (Epic S / Wave H2).
- Changing `hidden_need` from the admin UI.
- Replacing `session_id` in the workstation hash with a UUID in the path
  (`/play/{id}`) — optional polish after A5.

---

## 12. Risks (and the mitigation already in this plan)

| Risk | Mitigation |
|---|---|
| SMK-02 fails because Firebase lands in core | Verifier in adapters; forbidden import list extended |
| Existing tests break when APIs require auth | Default `AUTH_MODE=password`; Fake mode only in new tests |
| Session list still global | Registry + scoped queries (F1) before public Firebase |
| WS stays open | F3 in the same wave as F1, not a follow-up |
| Grade stays public | F2; instructor `doGrade()` sends token |
| Client-generated session ids | B3 server-issued ids |
| Locked out with no admin | Bootstrap email H-5 / D2 |
| Classroom this week needs the old flow | Password mode untouched |
| Admin “CRUD everything” leaks hidden needs to students | Admin-only payloads; challenger APIs unchanged |
| Token in WS query string logged by proxies | Prefer cookie in a hardening slice; short-lived tokens; don’t log query |

---

## 13. Definition of done (this initiative)

1. `AUTH_MODE=password`: today’s instructor password, unguarded workstation,
   **all existing tests green**.
2. `AUTH_MODE=firebase`: email sign-in; three roles; three dashboards;
   session APIs and WS scoped; admin CRUD as in §8; no password header.
3. `AUTH_MODE=fake`: CI coverage for 1–2 without a Google project.
4. Core still framework-free. Personas, director, interview assessor,
   mermaid, tickets extra credit, markdown export behave as now for an
   authorized user.
5. Human runbook H-1…H-7 executed on the real Firebase project before any
   hosted expose.

---

## 14. Relationship to other plans

| Doc | Relationship |
|---|---|
| `PLANNING.md` | Product architecture; do not violate ports/adapters. |
| `DEPLOYMENT-PLAN.md` | Hosted stack: Railway + Firebase Auth + Firestore. This file is Epic Q in detail. |
| `docs/CLASSROOM.md` | LAN password flow remains until an operator chooses Firebase. |

When A2+ ships, add a one-paragraph pointer in `DEPLOYMENT-PLAN.md` Epic Q
to this file so there is a single implementation backlog.
