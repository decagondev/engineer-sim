# Adding a desktop app

The workstation is a desktop shell with an app registry. Adding an app is one new
file plus one `register()` call — the shell (`static/shell.js`) never changes.
This is how you elaborate the immersion (email, a docs viewer, a ticket tracker,
a terminal) without touching what's already there.

## The contract

Create `static/apps/<id>.js` and register the app:

```js
SimApps.register({
  id: "tickets",              // unique; also used for the injected <style> id
  title: "Tickets",           // shown on the tile + window title bar
  accent: "#c56bff",          // tile glyph tint (optional)
  status: "not wired in",     // small caption under the tile (optional)
  icon: '<svg viewBox="0 0 24 24">…</svg>',   // inline SVG, stroke=currentColor
  css: `.tickets{…}`,         // optional; injected once, scope with a wrapper class
  visible(ctx) { return true; },   // optional; hide the tile for this session
  mount(root, ctx) {
    // root: the empty window body you render into
    // ctx:  { sid, scenario }  — the shared session id + parsed scenario;
    //       ctx.scenario.workflow = { kind: "doc"|"sandbox"|"repo", editable,
    //       needs_repo_url, submit_label, submit_hint } says how this session
    //       is worked (see docs/WORKSPACE-PLAN.md)
    root.innerHTML = `<div class="tickets">…</div>`;
    // …wire events, open sockets, fetch data…
    return { unmount() { /* close sockets, timers */ } };
  },
});
```

Then add one line to `static/index.html`:

```html
<script src="/static/apps/tickets.js"></script>
```

That's it — the tile appears on the desktop, opens in a window, and cleans up via
`unmount()` when closed.

## Shared modules

- `static/md.js` (`SimMD`): safe markdown + syntax highlighting for chat and previews.
- `static/diagram.js` (`SimDiagram`): draws ```mermaid fences and the design
  diagram with the vendored mermaid build, which it fetches on the first draw
  (no page ships the 3 MB script); retries a failed parse after the same
  label repair the server applies (`repair_mermaid`).
- `static/viz.js` (`SimViz`): inline-SVG stat tiles, bars, daily columns and
  meters for the dashboards (no library; palette validated for the dark surface).
- `static/editor.js` (`SimEditor`): one code editor for every app, backed by the
  vendored CodeMirror 5 under `static/vendor/codemirror/` (no CDN, so it works on a
  classroom LAN), loaded as one `bundle.min.js` (rebuild with
  `python tools/bundle_vendor.py`), with a `<textarea>` fallback:

  ```js
  const ed = SimEditor.mount(el, { path, text, readOnly, onSave, onChange });
  ed.getValue(); ed.setValue(t); ed.setPath(p); ed.setReadOnly(b); ed.focus(); ed.destroy();
  ```

## Rules of thumb
- **Scope your CSS** under a wrapper class (`.tickets .row`, not `.row`) so apps
  don't bleed into each other. The shared tokens (`--ink`, `--me`, `--mono`, …)
  are global — use them so every app feels like one machine.
- **State lives server-side, keyed by `ctx.sid`.** Apps mount/unmount freely; on
  reopen they should rebuild from the backend (chat replays its transcript, the
  workspace re-reads its handle). Don't hold important state only in the app.
- **A new app usually needs a new backend surface**, and that's a port/adapter +
  endpoint — the same pattern as chat's channels or the environment. Keep the
  domain logic in `sim/core`, the HTTP/WS in `sim/adapters/web`.
- **Stubs must read as inert.** If an app isn't wired in, say so (see
  `email.js` / `files.js`). A convincing-but-dead UI misleads playtesters —
  same principle as the grader's `calibrated:false` flag.

## What ships today
- **Team Chat** — full: personas, reveal ladder, the uninvited stakeholder,
  grade. Replies stream in as the model writes them (`delta` frames on the
  socket, then the stored message), the socket reconnects with backoff and
  replays what it missed, and the grade and the drawn design diagram sit in a
  collapsible strip above the conversation (folded on open, unfolded after
  Grade run).
- **Workspace** — real, per workflow: `sandbox` provisions the per-session dev box;
  `repo` links the learner's public repo on GitHub or the configured GitLab
  instance and offers **Connect GitHub / Connect GitLab** so Files can commit;
  hidden in `doc` (the folder is created on first use).
- **Mail** — real: threaded email with the client and stakeholders; the director
  can send inbound email (a scope change), which shows as a dock badge. Emails are
  recorded in the transcript and graded like chat.
- **Submit** — real, one button per workflow: `doc` submits DESIGN.md straight from
  the workspace; `sandbox` snapshots the dev box (patch paste kept as a collapsed
  offline fallback); `repo` submits the linked repo. Every path runs the same
  director triggers and opens the assessor on interview scenarios.
- **Files** — real: an editor with tabs, syntax highlighting, Save (Ctrl/Cmd+S,
  autosave), Refresh and a live markdown preview beside the editor (tables,
  code, mermaid drawn; opens by itself for DESIGN.md on a wide window). Writes
  are path-safe and, when hosted, kept in the database so a redeploy does not
  lose them. A linked repo is read-only until the learner connects their
  GitHub or GitLab account; then the button reads **Save & commit**, each save
  is one commit to their fork (autosave is off there so the history stays
  readable), and **What changed** shows the net diff against the starter.
  Mermaid is fetched the first time a diagram is drawn, not on page load.
- **Tickets** — real: a To Do / In Progress / Done board seeded with the client's
  asks; create and move tickets. Scoping actions are recorded in the transcript
  and graded.
