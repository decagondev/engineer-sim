SimApps.register({
  id: "workspace",
  title: "Workspace",
  accent: "#37d67a",
  icon: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 16h4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  css: `
  .ws{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:24px;text-align:center}
  .ws h2{margin:0;font-size:18px}
  .ws p{margin:0;color:var(--muted);max-width:420px;font-size:14px}
  .ws .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px;max-width:520px;width:100%;text-align:left}
  .ws .row{display:flex;gap:8px;align-items:baseline;margin:6px 0;font-size:13px}
  .ws .k{color:var(--muted);width:96px;flex:none}
  .ws .v{font-family:var(--mono);color:var(--text);word-break:break-all}
  .ws .cmd{background:var(--ink);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:12.5px/1.5 var(--mono);color:var(--sig);margin-top:10px;user-select:all}
  .ws .actions{display:flex;gap:10px;margin-top:14px}
  .ws button{border-radius:9px;padding:9px 14px;font:inherit;font-size:13px;cursor:pointer;border:1px solid var(--line);background:var(--panel-2);color:var(--text)}
  .ws button.primary{background:var(--me);border-color:var(--me);color:#fff;font-weight:600}
  .ws .err{color:#e5807a;font-size:13px}
  .ws .muted{color:var(--faint);font-size:12px}
  `,
  mount(root, ctx) {
    root.innerHTML = `<div class="ws"><div id="wsview">Loading workspace…</div></div>`;
    const view = root.querySelector("#wsview");
    const sid = ctx.sid;

    async function refresh() {
      let h;
      try { h = await (await fetch(`/api/session/${sid}/environment`)).json(); }
      catch (e) { view.innerHTML = `<p class="err">Couldn't reach the workspace service.</p>`; return; }
      if (h && h.error) { renderNone(h.error); return; }
      if (h && h.provisioned) renderReady(h); else renderNone();
    }

    function renderNone(err) {
      view.innerHTML =
        `<h2>Your dev box</h2>
         <p>Spin up an isolated workspace seeded with the project's starter repo.
            You build in it with your own editor or coding agent; your commits are
            what gets reviewed.</p>
         ${err ? `<p class="err">${err}</p>` : ""}
         <div class="actions" style="justify-content:center">
           <button class="primary" id="create">Create workspace</button>
         </div>`;
      view.querySelector("#create").onclick = create;
    }

    function renderReady(h) {
      view.innerHTML =
        `<h2>Workspace ready</h2>
         <div class="card">
           <div class="row"><span class="k">Location</span><span class="v">${h.workdir || "—"}</span></div>
           ${h.container ? `<div class="row"><span class="k">Container</span><span class="v">${h.container}</span></div>` : ""}
           ${h.connect_hint ? `<div class="muted">Connect a terminal:</div><div class="cmd">${h.connect_hint}</div>`
             : `<div class="muted">Open the folder above in your editor or coding agent.</div>`}
           <div class="actions">
             <button id="recheck">Refresh</button>
             <button id="reset">Reset workspace</button>
           </div>
         </div>
         <p class="muted">Commit as you go — the grader reads your git history.</p>`;
      view.querySelector("#recheck").onclick = refresh;
      view.querySelector("#reset").onclick = reset;
    }

    async function create() {
      view.innerHTML = `<p>Provisioning… first run may pull a container image.</p>`;
      let r;
      try { r = await (await fetch(`/api/session/${sid}/environment/provision`, { method: "POST" })).json(); }
      catch (e) { renderNone("Provisioning failed — is the environment service up?"); return; }
      if (r.error) { renderNone(r.error); return; }
      renderReady(r);
    }

    async function reset() {
      await fetch(`/api/session/${sid}/environment/teardown`, { method: "POST" });
      refresh();
    }

    refresh();
    return { unmount() {} };
  }
});
