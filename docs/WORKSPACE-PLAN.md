# Workspace plan: one path per scenario, editable files, repo-first when hosted

Status: implemented 2026-09-15 (waves 1–5). Section 1 records what was wrong before; the
rest is the design as built, with deviations listed in section 7. Read `CLAUDE.md` first for
the architecture vocabulary (ports, composition root, bundle, tracks, transcript markers).

## 1. What the code does today (verified)

The chain **submit → assessor → grade** works for the paste path and is broken for the repo
path. Checked against `sim/core/session/session_service.py`, the `/submit`, `/submit-repo`
and `/grade` routes in `sim/adapters/web/app.py`, and `tests/regression/test_interview.py`.

| Step | Paste path (`POST /submit`) | Repo path (`POST /submit-repo`) |
|---|---|---|
| Design text remembered | yes (`remember_design`) | **no** |
| Mermaid diagram rendered | yes | **no** |
| Director `submission` triggers fire | yes | yes |
| Assessor DM opens (`maybe_begin_assessment`) | yes, immediately on submit | **no**: `design_text` is empty, so it returns `[]` silently |
| Grader sees the assessor conversation | yes: the grader renders every channel of the transcript | yes |
| Grader sees the design | yes: `_enrich_build_record` appends DESIGN + mermaid | only the commit list and file names from GitHub; **never the document text** |
| Grader sees the build record | the pasted patch | GitHub commits + net diff vs the fork parent |

Other findings:

- **The "I'm done" cue is optional.** `after_submission` opens the assessor as soon as a
  design exists. The cue in `interview.py` only matters if the learner says "done" *before*
  submitting, in which case they get a nudge to submit. (`CLAUDE.md` said both were required;
  corrected.)
- **Design text does not survive a restart when hosted.** `SessionService._designs` is an
  in-process dict; the fallback `design_lookup` only reads `DESIGN.md` from the sandbox
  workdir, never from the submission store. On Railway the filesystem is ephemeral, so after
  a redeploy the assessor context says "they have not submitted a design yet" even though the
  submission row exists in Firestore.
- **Two confusing paths on screen.** The Submit app always shows A (GitHub) and B–E (zip +
  patch) regardless of track or hosting. The Workspace and Files apps assume a server-side
  sandbox that hosted learners never use for product scenarios. Nothing tells the learner
  which path applies to them.
- **Hosting is not a config concept.** `Config` has no notion of "deployed"; the Dockerfile
  installs git only so `local_folder` can baseline sandboxes. `ENV_PROVIDER=docker` cannot
  work on Railway (no daemon).
- `sim/scenarios/churn_dashboard/starter/.git` exists locally (untracked, left by the
  publish-to-GitHub steps). `LocalFolderEnvironment.provision` copies it into every sandbox.
  Harmless but worth deleting.

## 2. Goals

1. **One visible path per session.** The learner sees exactly one way to work and one way
   to submit, chosen by scenario track and by whether the server is hosted.
2. **Repo is the only path when deployed** for product scenarios. Local sandbox and patch
   paste exist only when running locally.
3. **Interview and systems scenarios are edited in the browser**, on every deployment. The
   workspace is a server-side folder seeded from the starter; the learner edits `DESIGN.md`
   (and `TICKETS.md`) in a real editor and clicks Submit. No pasting.
4. **Files app is an editor**, not a viewer: tree, tabs, syntax highlighting, save, refresh,
   read-only mode when browsing a GitHub repo.
5. **Every path feeds the assessor and the grader** the same way.
6. Stay inside the existing architecture: pure decision in `sim/core`, I/O behind ports,
   wiring in the composition root, one dock app per file.

## 3. The workflow matrix

A session's **workflow** is a pure function of `(scenario.track, config.hosted)`:

| Track | Local run | Hosted (Railway) |
|---|---|---|
| `interview` (`iv_*`) | **doc** | **doc** |
| `systems` (`sys_*`) | **doc** | **doc** |
| `product` | **sandbox** | **repo** |

Each workflow defines what the three apps do:

| | `doc` | `sandbox` | `repo` |
|---|---|---|---|
| Workspace app | hidden (auto-provisioned) | provision / reset dev box (as today) | "Link your repo": paste URL once, shows linked repo + HEAD |
| Files app | tree + **editor**, Save, Refresh | tree + **editor**, Save, Refresh | tree + viewer, read-only until the learner connects GitHub / GitLab, then Save commits; Refresh re-reads HEAD |
| Submit app | one button: **Submit DESIGN.md** (reads it from the workspace) | one button: **Submit from workspace** (build record = sandbox git); patch paste kept as a collapsed fallback | one button: **Submit for grading** (snapshots HEAD sha); no zip, no patch |
| Build record for grader | DESIGN.md + TICKETS.md text + workdir git log | sandbox git log + net diff | GitHub commits + net diff vs fork + text of `DESIGN.md`/`README.md` if present |
| Assessor / design triggers | on Submit | on Submit | on Submit |

`config.hosted` comes from a new env var `WORK_MODE` = `auto` (default) | `local` | `hosted`.
`auto` means hosted when `AUTH_MODE=firebase` or `PERSISTENCE=firestore`. The explicit
values exist so a classroom LAN server (`serve.py`) can force `local` and a test can force
`hosted` without Firebase.

## 4. Design

### 4.1 Core (pure)

`sim/core/workflow.py`

```python
@dataclass(frozen=True)
class Workflow:
    kind: str            # "doc" | "sandbox" | "repo"
    editable: bool       # Files app may write
    submit_label: str    # copy for the one Submit button
    needs_repo_url: bool # Workspace app asks for a GitHub URL

def resolve_workflow(track: str, hosted: bool) -> Workflow
```

Tested in isolation with the six cells of the matrix. Exposed to the front end as
`workflow` on `/api/session/{id}/scenario` and `/api/scenarios`, next to `track`.

`sim/core/ports/workspace.py` grows a writer:

```python
class WorkspaceFiles(Protocol):           # replaces WorkspaceReader (keep the old name as alias)
    def list_dir(self, root: str, relpath: str = "") -> Sequence[FileEntry]: ...
    def read_file(self, root: str, relpath: str) -> FileContent: ...
    def write_file(self, root: str, relpath: str, text: str) -> None: ...   # raises ReadOnlyWorkspace
    def refresh(self, root: str) -> str: ...                                 # returns a revision label
```

`root` is whatever the adapter needs: a workdir path for the folder adapter, a repo URL for
the GitHub adapter. The web layer never inspects it.

`sim/core/ports/session_files.py`: a small durable overlay so hosted `doc` workspaces survive
restarts without adding a third database:

```python
class SessionFileStore(Protocol):
    def put(self, session_id: str, relpath: str, text: str, ts: str) -> None: ...
    def get(self, session_id: str, relpath: str) -> Optional[str]: ...
    def list(self, session_id: str) -> Sequence[str]: ...
    def delete_session(self, session_id: str) -> None: ...
```

Only files the learner edited are stored; the starter supplies the rest. Sqlite table
`session_files(session_id, relpath, content, ts)`; Firestore collection
`sessions/{sid}/files/{encoded relpath}` (1 MB cap per file is fine for design docs; reject
larger writes with a clear error).

`sim/core/workspace/workspace_service.py` (new, pure) composes the two:

- `read(session, path)`: overlay hit → return it; else the adapter.
- `write(session, path, text)`: overlay put, then adapter write (so git in the workdir still
  records the edit for the build record). Adapter write failures are logged, not fatal.
- `hydrate(session)`: after `Environment.provision`, replay the overlay onto the workdir.
  Called from the bundle when a handle is first obtained in a process. This is what makes
  Railway restarts invisible to the learner.
- `submit_doc(session)`: read `DESIGN.md` (+ `TICKETS.md` if present), return the text.

`SessionService.design_text` fallback order becomes: memory → latest submission of kind
`doc`/`patch` (the durable record) → workdir file. This alone fixes the hosted restart bug
and is the first, smallest change to ship.

### 4.2 Adapters

- `sim/adapters/workspace/local_files.py`: today's `LocalWorkspaceReader` plus `write_file`
  (path-safe, refuses `.git/`, creates parent dirs, atomic write via temp file + rename) and
  `refresh` returning the workdir's HEAD short sha or a mtime stamp.
- `sim/adapters/workspace/github_files.py`: `GitHubWorkspaceFiles`, read-only. `list_dir`
  and `read_file` use `GET /repos/{o}/{r}/contents/{path}` (base64 decode, same size and
  binary rules as the local reader). One `git/trees?recursive=1` call per refresh is cached
  in memory keyed by `(repo, head_sha)`; `refresh` re-reads the default branch sha and drops
  the cache when it changed. Reuses `parse_repo` and `_get` from `github_observer.py`
  (extract them into `sim/adapters/build/github_api.py` so both adapters share the token,
  rate-limit and error mapping). `write_file` raises `ReadOnlyWorkspace`.
- `sim/adapters/persistence/sqlite_session_files.py`, `firestore_store.py::FirestoreSessionFileStore`,
  and `memory_session_files.py` for tests; registered in `stores.py::build_stores`.
- `GitHostBuildObserver.summary` additionally fetches `DESIGN.md` and `README.md` contents
  (if present, capped at 12 k chars) so the grader and assessor can read the document when a
  repo is the source.

### 4.3 Session settings

The settings store already holds per-session scenario and level. Add
`set_session_repo_url` / `get_session_repo_url` (sqlite + Firestore + memory). The repo URL is
validated with `GitHostBuildObserver.validate` when linked, and recorded in the transcript
as `[reveal] Linked repo: <url>` so instructors see it in replay.

### 4.4 Web layer

Routes (all under `/api/session/{id}`):

| Route | Change |
|---|---|
| `GET /scenario` | add `workflow: {kind, editable, submit_label, needs_repo_url}` |
| `GET /files/list`, `GET /files/read` | resolve the root from the workflow: `doc`/`sandbox` → sandbox workdir (auto-provision for `doc`), `repo` → linked repo URL (409 with "link your repo first" when missing) |
| `PUT /files/write` (new) | body `{path, text}`; 405 in `repo` workflow; writes through `WorkspaceService`; returns `{path, revision}` |
| `POST /files/refresh` (new) | returns `{revision}`; for `repo` this re-reads HEAD |
| `POST /workspace/repo` (new) | body `{url}`; validates, stores, appends the transcript marker |
| `POST /submit-doc` (new) | reads `DESIGN.md` via `WorkspaceService.submit_doc`, saves a submission `kind="doc"`, then the existing `remember_design` → `_maybe_diagram` → `after_submission` chain |
| `POST /submit-repo` | keep; add: if the repo contains `DESIGN.md`, `remember_design` with its text so interview/systems sessions that somehow arrive here still open the assessor |
| `POST /submit` (patch) | keep; return 405 when `config.hosted` |
| `GET /starter.zip` | return 404 when `config.hosted` |
| `POST /grade` | build-record resolution moves into one helper `_build_record_for(session)` that switches on the workflow (table in section 3) instead of the current `payload → latest submission → sandbox` guesswork |

The environment routes stay as they are. In the `doc` workflow the bundle provisions the
workdir on first file access, so the learner never sees a "create workspace" step.

### 4.5 Front end

`static/shell.js` reads `ctx.scenario.workflow` and passes it to every app via `ctx`. The dock
hides the Workspace tile in the `doc` workflow (`register({..., visible(ctx) })` is a one-line
addition to the shell contract in `docs/APPS.md`).

`static/editor.js` (new, shell-level module like `md.js`):

```js
SimEditor.mount(el, { path, text, readOnly, onSave })  // returns { getValue, setValue, focus, destroy }
```

Backed by **CodeMirror 5** vendored under `static/vendor/codemirror/` (core `lib/codemirror.js`
+ `codemirror.css`, modes: markdown, python, javascript, yaml, css, htmlmixed, sql, shell;
addons: active-line, search, matchbrackets). It is plain script files, MIT, ~350 KB, needs no
build step, and works offline on a classroom LAN (this repo deliberately has no CDN
dependencies; see the header of `md.js`). Theme: a small `sim-dark.css` that maps CodeMirror
token classes to the shell's existing `--ink`, `--panel`, `--me`, `--sig` tokens so it looks
like the rest of the workstation. If the vendor files fail to load, `SimEditor` falls back to
a `<textarea>` with the same API, so the app never dead-ends.

Monaco (VS Code's editor) was considered and rejected for v1: 5 MB+, needs web workers and a
loader, and the project has no bundler. CodeMirror 6 was rejected for the same reason
(ESM-only, needs a build). Either can replace the internals later because apps only talk to
`SimEditor`.

`static/apps/files.js` becomes the editor app:

- Left: tree with folders expanded on click (as today) plus a **Refresh** button in the bar
  that calls `/files/refresh` and reloads the current directory.
- Right: tab strip (one tab per open file, dirty dot), `SimEditor` below, status bar showing
  `workspace @ <revision>` or `github.com/owner/repo @ <sha>` and **read-only** when the
  workflow is `repo`.
- Save: Ctrl/Cmd+S and a button; disabled in `repo`. Markdown files get a **Preview** toggle
  that renders through `md.js`.
- Mounting in `doc`/`sandbox` opens `DESIGN.md` automatically when it exists.

`static/apps/workspace.js`: branches on `ctx.scenario.workflow.kind`. `sandbox` is today's
UI. `repo` is the link form: starter fork link (from `starter_url`), URL input, **Link repo**,
then the linked repo, HEAD sha, and "Open Files to browse what you pushed". `doc` is never
shown.

`static/apps/submit.js`: renders exactly one section per workflow (section 3), plus the
submission history. The four-step patch tutorial moves under a collapsed "Offline fallback"
disclosure in `sandbox` only.

### 4.6 Assessor and grading, end to end

After this plan every workflow ends in the same server-side call sequence:

```
submissions.save(kind)  →  remember_design (doc text if any)  →  _maybe_diagram (interview)
  →  after_submission: director `submission` triggers, then maybe_begin_assessment
```

and `/grade` always assembles: transcript (all channels, so the assessor DM is included) +
workflow build record + design text + mermaid + optional tickets. Add one regression test per
workflow that submits, asserts the `[fired:assessment_open]` marker (interview) or the design
review email/ticket (systems), then grades with the fake LLM and asserts the design text
reached the grader prompt (`FakeLLMClient` records its inputs).

## 5. Delivery waves

Each wave is shippable on its own and keeps `pytest` green.

**W1. Correctness (small, do first).**
`design_text` reads the latest submission before the workdir; `submit_repo` pulls
`DESIGN.md` from the repo into `remember_design`; `GitHostBuildObserver.summary` includes
document text. Tests: hosted-restart simulation (new `SessionService` over the same stores
must still open the assessor); repo submission on an `iv_*` scenario opens the assessor.

**W2. Workflow resolution.**
`WORK_MODE` in `Config`, `sim/core/workflow.py`, `workflow` in the scenario payload, hosted
gating on `/submit` and `/starter.zip`, `_build_record_for`. Submit app renders one section.
Tests: matrix unit test; `Config(hosted=True)` returns 405 on patch submit.

**W3. Editable workspace for `doc` and `sandbox`.**
`WorkspaceFiles` port + local adapter with `write_file`, `SessionFileStore` (sqlite,
Firestore, memory), `WorkspaceService` with hydrate, `/files/write`, `/files/refresh`,
`/submit-doc`. Vendor CodeMirror, add `editor.js`, rewrite `files.js`. Auto-provision on
first file access in `doc`. Tests: write is path-safe and refuses `.git/`; overlay replays
after a fresh provision; `submit-doc` opens the assessor without any pasted text.

**W4. Repo browsing for `repo`.**
`github_api.py` extraction, `GitHubWorkspaceFiles`, session repo URL setting,
`/workspace/repo`, Files app read-only mode with refresh, Workspace app link form. Tests:
adapter against a recorded fixture of the GitHub JSON (no network); refresh invalidates on
sha change; write returns 405.

**W5. Polish and docs.**
Hide Workspace tile in `doc`; markdown preview; `docs/APPS.md` (`visible(ctx)`, `SimEditor`),
`GET_STARTED_STUDENT.md`, `docs/PUBLISH-SCENARIOS.md`, `CLAUDE.md` (workflow matrix, new env
var), `DEPLOYMENT-PLAN.md` (record `WORK_MODE`). Delete the stray
`sim/scenarios/churn_dashboard/starter/.git`.

## 6. Decisions and open questions

- **Editing a repo from the browser: delivered (roadmap item 9, then GitLab).** Connect
  GitHub / Connect GitLab (device flow) store a per-user token; `RepoWorkspaceFiles.write_file`
  commits through the host's file API when that user's scope allows. The `WorkspaceFiles`
  port did not change. Both forges sit behind `ports/repo_host.py` and a URL router; see
  `docs/REPO-HOSTS.md`. Learners without a connection still push from their machine and
  press Refresh.
- **Ephemeral hosted filesystem.** The overlay store is the source of truth for edited files;
  the workdir is a cache that also gives the grader a git log. Losing the workdir on redeploy
  loses only the commit timeline of a design doc, which the interview rubric does not weight.
- **Firestore 1 MB per document.** One document per edited file; refuse writes over ~900 KB
  with a message. Design docs are kilobytes.
- **Rate limits.** Repo browsing multiplies GitHub reads. `GITHUB_TOKEN` is the classroom
  bucket and should be set on Railway; the tree cache keeps it to one call per refresh plus
  one per opened file. Challengers can also store their own GitHub token in Settings (same
  BYOK mechanism as the Groq key); every GitHub call made inside their request then uses
  their token, so the limit scales with the class.
- **Should systems scenarios also allow a repo?** Not in v1. Their starters are documents,
  and the design-review triggers read the submitted text, so `doc` fits. Revisit if an
  instructor wants code in a systems scenario.

## 7. As built: deviations from the plan

- **Sandbox submit is a real endpoint.** `POST /submit-workspace` commits the working tree
  ("submitted from workspace"), records a `workspace` submission and runs the director, so
  product scenarios' `submission` triggers fire without a patch or a repo.
- **`submit-doc` also snapshots.** The doc workflow commits the folder on submit so the
  sandbox git log in the build record shows the browser edits.
- **Repo link is a session setting**, and `submit-repo` falls back to it when the body has no
  URL, and stores a URL it is given, so the grader and Files agree on one repo.
- **`SessionManager.lookup_design`** replaced the plan's `SessionService` change: the order is
  latest submission (`doc`, or `patch` on a design track) → repo `DESIGN.md` → workdir file.
  A product patch is never treated as a design, which also removed a duplicate in the grader
  prompt.
- **`GitHubApi`** (`adapters/build/github_api.py`) is the shared client; both the build
  observer and the files adapter take an injectable `fetch`, and the tests use recorded JSON.
- **Autosave.** The Files app saves dirty tabs every 20 s and on unmount, in addition to
  Ctrl/Cmd+S, because a lost design doc is the worst failure this feature can have.
- **Hosted product scenarios refuse `/submit` and `/starter.zip`** (405 / 404), while design
  tracks still accept a pasted design when hosted, as a manual fallback.

Verified in a browser against the fake model: interview session (edit, save, submit,
assessor opens, diagram rendered), product session locally (create dev box, edit
`src/analysis.py`, Ctrl+S, submit from workspace), and product session with
`WORK_MODE=hosted` (link `octocat/Hello-World`, browse read-only, Refresh, submit button
enabled, no patch fallback shown).
