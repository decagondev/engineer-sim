# Roadmap

What to build next, in the order that pays off soonest. The implementation
design for every item, following the ports-and-adapters rules, is in
`docs/ROADMAP-PLAN.md`. Sizes are honest guesses
for one person: **S** under a day, **M** two to four days, **L** a week or more.
Each item names the files it touches so it can be picked up cold. Delivered work is
summarised at the end of `PLANNING.md`.

## Now: close the loop on grading

These turn the grader from "directional" into something an instructor would stand
behind, which is the one caveat still printed on every grade.

1. **Instructor score override and comments (M).** On the replay's Assessment panel,
   let the instructor adjust each criterion, add a comment, and save. Store it next to
   the LLM grade (`ports/grades.py` gains `human` fields; `sqlite_grades.py`,
   `firestore_store.py`). The challenger's Grade run shows the human score when one
   exists; the export includes both. This is the input calibration has been waiting for.
2. **Calibration from the dashboard (M).** Every session with a human score becomes a
   fixture automatically (`sim/app/save_fixture.py` already knows the shape). An admin
   button runs `sim/app/calibrate.py --consistency` in a background thread against the
   real provider, shows agreement per criterion, and offers to flip
   `grader_calibrated` when it passes. Touches `/admin` Settings and `calibration/`.
3. **Evidence that links back (S).** Grade evidence strings are quotes from the
   transcript; make each one a link that scrolls the replay timeline to the message it
   cites (`instructor.html` `renderGrade`, `renderEv` gets `data-id`).
4. **Cohort results (M).** An instructor view per cohort and scenario: score
   distribution per criterion, who has not submitted, export as CSV. Reuses
   `_session_stats` and `SimViz`; add `/api/instructor/cohorts/{cid}/results`.

## Next: the interview experience

5. **Visible timebox (S).** The brief says "twenty minutes" but nothing counts. A timer
   in the workstation menubar from session start, configurable per scenario
   (`timebox_minutes` in `scenario.yaml`, shown by `shell.js`); the assessor's opening
   line notes when it ran over. No enforcement, just pressure.
6. **Editor polish (S each).** Find and replace across the open file (CodeMirror's
   search addon is vendored, just unbound), a resizable split between editor and
   preview, a word count in the status bar for `DESIGN.md`, Ctrl/Cmd+B/I in markdown,
   and "insert diagram template" that drops a starter ```mermaid block. All in
   `static/apps/files.js` and `static/editor.js`.
7. **Diff against the starter (M).** A "What changed" tab in Files showing a unified
   diff of the workspace against the starter commit (the sandbox is git-baselined;
   `GitBuildObserver` already computes the net diff). Read-only, highlighted with
   `SimMD.highlight(…, "diff")`.
8. **Assessor follow-through (S).** Cap or surface the number of assessor questions
   answered, and have the grader see it: the rubric's communication criterion cites
   "answered 4 of 5 probes". `session_service.py` counts assessor turns; `_enrich_build_record`.

## Then: hosted build scenarios without leaving the browser

9. **GitHub OAuth so Files can write to a linked repo (L).** Device-flow sign-in from
   the Workspace app, token stored like the personal token today, `GitHubWorkspaceFiles`
   gets a real `write_file` through the contents API with a commit per save. The port
   already has the method; the apps need no change. Turns the hosted `repo` workflow
   into the same experience as the local dev box.
10. **Live instructor view (M).** The replay opens on a WebSocket instead of polling, so
    an instructor can watch a session as it happens and the "needs attention" list
    updates without Refresh. `adapters/web/app.py` gains a read-only `/ws/watch/{sid}`.

## Operations and performance

11. **Query by owner in Firestore (S).** `list_by_owner` and `list_by_assignee` filter a
    full stream in memory; use `where("owner_uid", "==", uid)` with a composite index
    so an instructor with ten sessions on a server with a thousand does not stream them
    all. `firestore_store.py`, plus an index in the Firebase console.
12. **Challenger dashboard (S).** `/api/me/sessions` already avoids per-session
    reads (verified); show each session's state and grade there so a challenger
    sees "graded 78%" on their own list.
13. **Session retention (M).** Admin action "archive sessions older than N days":
    export the markdown audit to the asset store, then cascade-delete. Keeps Firestore
    reads bounded as terms accumulate.
14. **Audit log (M).** Admin writes (user create/delete, role change, cohort edits,
    settings) appended to `meta/audit` with actor and time; a tab under `/admin`.
    Listed in `auth-plan.md` A7 and still open.
15. **Health that fails loudly (S).** `/health` already reports commit and model; add
    a `checks` block (Firestore read, model ping with a five-second timeout, key
    presence) and have Railway's health check read it, so a bad key or a Firestore
    outage shows as a failed deploy instead of a slow dashboard.

## Later, if the class asks for it

- Scenario authoring UI: edit `scenario.yaml` fields and the reveal ladder from
  `/admin`, with the interview generator (`tools/write_interview_scenarios.py`) as
  a template picker.
- Persona voice: TTS for the interviewer's brief and the assessor's questions, so an
  interview feels spoken (browser SpeechSynthesis needs no key).
- Mobile workstation: the dock and Files layout at phone width for reading and chat
  (editing stays desktop).
- A second hosted model provider behind `LLM_PROVIDER` for failover when Groq is
  rate-limited class-wide (Anthropic is already an adapter; the missing piece is
  automatic fallback in `scoped_client.py`).
