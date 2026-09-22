# Quality-of-life and optimisation plan

Twelve items from a read of the codebase on 2026-09-22, in the order they are
built. Each keeps the existing shape: a pure decision in `sim/core/`, I/O behind a
port, one adapter per concern, wiring only in the composition root, and a test
that fails before the change and passes after. Nothing here adds a database, a
build step the tests do not check, or a dependency.

Evidence for each item is in the "Why" line so the change can be judged cold.

## Group A: what learners feel (first)

### A1. One user-directory read per request

**Why.** The Groq key resolver, the GitHub token resolver, the GitLab token
resolver and both `can_write` checks each call `users.get(uid)`; the auth layer
already fetched the same record. A Files save on a linked repo is four to five
Firestore round trips of a few hundred milliseconds each.

**Design.** `adapters/llm/request_context.py` gains a per-request memo next to
`current_uid`: `current_user(users)` returns the cached `UserRecord` for the
current uid, fetching once; `prime_user(rec)` lets the auth layer store the
record it already has; `set_current_uid` resets the memo. Resolvers and the
`can_write` closures call `current_user(users)`. The websocket loop sets the uid
and memo the same way. No port changes; `sim/core` untouched.

**Test.** `tests/unit/test_request_memo.py`: count `users` document reads on the
fake Firestore for a Files write and an `/api/auth/me` round trip; at most one
read after the auth gate.

### A2. No autosave commits on a connected repo

**Why.** `files.js` autosaves dirty tabs every 20 s whenever the workflow is
editable, and on the repo workflow every save is a commit. An hour of typing
leaves a hundred "Edit DESIGN.md from the workstation" commits in the fork and
in the build record the grader reads.

**Design.** The timer runs only when `workflow.writes_to_repo` is false. On the
repo workflow the Save button reads "Save & commit", the status line says a
commit was made, and the commit message becomes `Update <path> via the
workstation`. The unmount save stays (one commit beats losing work).

**Test.** A regression test for the commit message; the Files behaviour is
documented in `docs/APPS.md` and the challenger guide.

### A3. Mermaid loads only when a diagram is drawn

**Why.** The vendored mermaid build is 3.2 MB and is the largest thing on the
workstation page, loaded before Team Chat opens. The Railway edge already gzips
static files (checked with `curl`), so a gzip middleware is not needed.

**Design.** `diagram.js` gains `ensure()`: injects the vendored script once and
resolves when `window.mermaid` exists; `render` awaits it. The `<script>` tags
leave `index.html` and `instructor.html`. Behaviour without the file is
unchanged (fences stay code blocks).

**Test.** Smoke test: no page ships the mermaid tag; `diagram.js` names the
vendored path so the lazy load cannot silently point elsewhere.

### A4. Team Chat reconnects on its own

**Why.** `ws.onclose` disables Send and tells the learner to reopen the app; the
challenger guide's troubleshooting says "refresh the page".

**Design.** `connect()` schedules a retry with exponential backoff (1 s doubling
to 30 s, with jitter) unless the app was unmounted; on reopen it replays the
transcript through the existing `incoming(..., {replay: true})` path (the `seen`
set de-duplicates), re-enables Send and posts a one-line "reconnected" signal.

**Test.** None automatable in the Python suite; the guide's troubleshooting entry
is rewritten.

## Group B: smaller wins

### B5. Conditional requests to GitHub

**Why.** GitHub does not count 304 responses against the rate limit; the client
never sends an ETag, so every Refresh and tree re-read spends budget.

**Design.** `github_api._default_fetch` keeps a bounded (500 entry) ETag cache
keyed by path: sends `If-None-Match`, returns the cached body on 304. Bodies are
public data, so the cache is shared across tokens.

**Test.** Unit test with a stubbed `urlopen` that answers 304 the second time.

### B6. Bounded repo snapshot cache

**Design.** `RepoWorkspaceFiles._cache` becomes an LRU of 200 repos.

**Test.** Unit test: 201 roots, the first is evicted.

### B7. Fewer GitLab calls per read

**Why.** Every host method starts with the project lookup; a file read without a
known revision costs project + branch + file.

**Design.** `GitLabHost` caches the project JSON per ref for 5 s. Branch tips
are never cached, so Refresh stays truthful.

**Test.** Count project calls across `info`, `head`, `commits`, `file_text` on the
recorded fake within the window.

### B8. Cheaper admin-exists check

**Why.** `FirestoreUserDirectory.count_role` streams the whole users collection;
it runs during sign-in for the bootstrap-admin rule.

**Design.** Firestore adapter uses the `count()` aggregation when the client
supports it and falls back to the stream otherwise. `AuthServices` remembers that
an admin exists after the first positive answer, so the query runs at most once
per process.

**Test.** Fake Firestore without `count()` (fallback path) and a stub with it;
the memo prevents a second query.

### B9. Streamed persona replies

**Why.** A turn is two model calls in sequence (reveal judge, then persona) and
the whole reply lands at once; on the slow model the typing indicator runs for
many seconds.

**Design.** Port: `ports/llm.py` adds `StreamingLLMClient` (`stream(system,
messages, on_delta) -> str`) next to `LLMClient`, plus a pure helper
`complete_with_deltas(llm, ..., on_delta)` that uses `stream` when the client has
it and otherwise calls `complete` and emits the whole text once. Adapters: Groq
implements `stream` over the SSE endpoint; Ollama and Anthropic stay
non-streaming; the failover and scoped wrappers delegate and only fail over when
no delta has been emitted yet; the fake client emits three chunks so the path
is exercised. Core: `PersonaResponder.respond(..., on_delta=None)` and
`SessionService.post_tester_message(..., on_delta=None)`. Web: the socket loop
hands a thread-safe callback that pushes `{"kind": "delta", ...}` frames through
an asyncio queue while the turn runs on the threadpool; the final message frame
is unchanged, so old clients keep working. Chat UI: a provisional bubble grows
with deltas and is replaced by the final message.

**Test.** Unit: SSE parsing with a fake transport; the helper's fallback path;
failover after a partial stream is refused. Regression: the websocket test
receives at least one delta frame before the final frame with the fake client.

## Group C: developer quality of life

### C10. Split the web factory into routers

**Why.** `sim/adapters/web/app.py` is 3,140 lines of closures in one function.

**Design.** A `sim/adapters/web/routes/` package. `context.py` defines
`WebContext`: the app, manager and the shared helpers (`b`, `_workflow`,
`_actor`, `_cached`, `_after_mutation`, ...) that more than one area uses,
attached as plain attributes so modules stay closures over `ctx`. One module per
area, each exposing `register(app, ctx)`: `shell` (pages, health, scenarios),
`session` (lifecycle, transcript, grading, diagram, submissions, environment),
`files`, `tickets_mail`, `me` (auth, settings, connect), `instructor`
(sessions, cohorts, settings, replay, export), `dashboards` (listing helpers,
caches, overview), `admin` (users, cohorts, sessions, settings, calibration,
scenarios, audit, archive), `live` (websockets). `create_web_app` becomes the
middleware plus the registration order. Behaviour is identical; the suite is the
proof. Registration order matters only for helpers, which live on `ctx` before
the module that needs them runs.

**Test.** The whole suite, unchanged, plus a smoke test that every route path
present before the split is still registered (a frozen list).

### C11. A green suite on Windows

**Design.** `test_files02` writes its fixture with `write_bytes`; the two
teardown failures get a shared `remove_tree` in
`sim/adapters/environment/fsutil.py` that clears the read-only bit and retries,
used by both environments.

### C12. One CodeMirror bundle

**Why.** The workstation loads 29 script tags, 16 of them CodeMirror files.

**Design.** `tools/bundle_vendor.py` concatenates the CodeMirror core, modes and
addons into `static/vendor/codemirror/bundle.min.js` with a manifest of the
parts and their hashes; `index.html` and `admin.html` load one tag. The bundle
is committed; `--check` verifies it matches the parts.

**Test.** Smoke test runs the check so a stale bundle fails CI.

## Order and commits

One commit per item, in the order above; the suite runs before each. Items A1,
B5, B6, B7 and B8 have no user-visible change and can ship together if their
tests pass; A2, A3, A4 and B9 change the pages and are worth a look in a browser
before pushing.
