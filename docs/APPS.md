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
  mount(root, ctx) {
    // root: the empty window body you render into
    // ctx:  { sid, scenario }  — the shared session id + parsed scenario
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
- **Team Chat** — full: personas, reveal ladder, the uninvited stakeholder, grade.
- **Workspace** — real: provisions the per-session sandbox, shows how to connect.
- **Mail** — real: threaded email with the client and stakeholders; the director
  can send inbound email (a scope change), which shows as a dock badge. Emails are
  recorded in the transcript and graded like chat.
- **Submit** — real: download the scenario starter, build on your own machine,
  and submit a git patch back for grading (the classroom/LAN path).
- **Files** — real: read-only browser of the per-session sandbox (starter repo
  + your committed work), path-safe.
- **Tickets** — real: a To Do / In Progress / Done board seeded with the client's
  asks; create and move tickets. Scoping actions are recorded in the transcript
  and graded.
