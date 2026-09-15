SimApps.register({
  id: "workspace",
  title: "Workspace",
  accent: "#37d67a",
  icon: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 16h4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  // hidden in the doc workflow: the folder is created on first use, nothing to manage
  visible(ctx) { const wf = ctx.scenario && ctx.scenario.workflow; return !wf || wf.kind !== "doc"; },
  css: `
  .ws{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:24px;text-align:center;overflow-y:auto}
  .ws h2{margin:0;font-size:18px}
  .ws p{margin:0;color:var(--muted);max-width:460px;font-size:14px;line-height:1.55}
  .ws .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px;max-width:560px;width:100%;text-align:left}
  .ws .row{display:flex;gap:8px;align-items:baseline;margin:6px 0;font-size:13px}
  .ws .k{color:var(--muted);width:96px;flex:none}
  .ws .v{font-family:var(--mono);color:var(--text);word-break:break-all}
  .ws .v a{color:var(--me)}
  .ws .cmd{background:var(--ink);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:12.5px/1.5 var(--mono);color:var(--sig);margin-top:10px;user-select:all;white-space:pre-wrap;text-align:left}
  .ws .actions{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
  .ws button{border-radius:9px;padding:9px 14px;font:inherit;font-size:13px;cursor:pointer;border:1px solid var(--line);background:var(--panel-2);color:var(--text)}
  .ws button.primary{background:var(--me);border-color:var(--me);color:#fff;font-weight:600}
  .ws input{flex:1;min-width:240px;background:var(--ink);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:9px 12px;font:inherit}
  .ws input:focus{border-color:var(--me);outline:none}
  .ws .err{color:#e5807a;font-size:13px}
  .ws .ok{color:var(--ok,#37d67a);font-size:13px}
  .ws .muted{color:var(--faint);font-size:12px}
  `,
  mount(root, ctx) {
    root.innerHTML = `<div class="ws"><div id="wsview">Loading workspace…</div></div>`;
    const view = root.querySelector("#wsview");
    const sid = ctx.sid;
    const wf = (ctx.scenario && ctx.scenario.workflow) || { kind: "sandbox" };
    const esc = s => { const d = document.createElement("div"); d.textContent = s || ""; return d.innerHTML; };
    const api = (p, o) => fetch(`/api/session/${sid}${p}`, o);

    // ---- repo workflow: link a public GitHub repo ----------------------------
    async function repoView(note) {
      let cur = "";
      try { cur = (await (await api(`/workspace/repo`)).json()).url || ""; } catch (e) {}
      const starter = ctx.scenario && ctx.scenario.starter_url;
      view.innerHTML =
        `<h2>${cur ? "Your repo is linked" : "Link your repo"}</h2>
         <p>You work on your own machine with git. Fork the starter, push as you go,
            and link your <b>public</b> repo here. The Files app browses what you have
            pushed, and grading reads your commits.</p>
         <div class="card">
           <div class="row"><span class="k">Starter</span><span class="v">${starter
             ? `<a href="${esc(starter)}" target="_blank" rel="noopener">${esc(starter)}</a> — fork it`
             : `<span class="muted">not set yet — ask your instructor</span>`}</span></div>
           <div class="cmd"># after forking on GitHub:
git clone https://github.com/&lt;you&gt;/&lt;your-fork&gt;.git
cd &lt;your-fork&gt;
# …do the work, committing as you go…
git push</div>
           <div class="row" style="margin-top:14px"><span class="k">Your repo</span>
             <input id="url" placeholder="https://github.com/you/your-fork" value="${esc(cur)}"/></div>
           <div class="actions">
             <button class="primary" id="link">${cur ? "Update link" : "Link repo"}</button>
             ${cur ? `<button id="files">Open Files</button><button id="refresh">Refresh from GitHub</button>` : ""}
           </div>
           <div id="note" style="margin-top:8px">${note || ""}</div>
         </div>
         <p class="muted">Only public repos can be read. Pushed changes show up after Refresh.</p>`;
      view.querySelector("#link").onclick = async () => {
        const url = view.querySelector("#url").value.trim();
        if (!url) { view.querySelector("#note").innerHTML = `<span class="err">Paste your repo URL.</span>`; return; }
        view.querySelector("#note").textContent = "Checking on GitHub…";
        let r;
        try { r = await (await api(`/workspace/repo`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) })).json(); }
        catch (e) { view.querySelector("#note").innerHTML = `<span class="err">Could not reach the server.</span>`; return; }
        if (r.error) { view.querySelector("#note").innerHTML = `<span class="err">${esc(r.error)}</span>`; return; }
        repoView(`<span class="ok">✓ ${esc(r.message)}. Open Files to browse it.</span>`);
      };
      const f = view.querySelector("#files"); if (f) f.onclick = () => SimApps.open("files");
      const rf = view.querySelector("#refresh"); if (rf) rf.onclick = async () => {
        view.querySelector("#note").textContent = "Refreshing…";
        try { const r = await (await api(`/files/refresh`, { method: "POST" })).json();
          view.querySelector("#note").innerHTML = r.error ? `<span class="err">${esc(r.error)}</span>` : `<span class="ok">✓ Now at ${esc(r.revision)}</span>`;
        } catch (e) { view.querySelector("#note").innerHTML = `<span class="err">Refresh failed.</span>`; }
      };
    }

    // ---- doc workflow (normally hidden): nothing to manage ----------------------
    function docView() {
      view.innerHTML =
        `<h2>Your workspace is ready</h2>
         <p>The starter documents are already in your workspace. Open <b>Files</b> to write
            DESIGN.md in the editor, then use <b>Submit</b> when it is done.</p>
         <div class="actions" style="justify-content:center"><button class="primary" id="files">Open Files</button></div>`;
      view.querySelector("#files").onclick = () => SimApps.open("files");
    }

    // ---- sandbox workflow: the server-side dev box ---------------------------
    async function refresh() {
      let h;
      try { h = await (await api(`/environment`)).json(); }
      catch (e) { view.innerHTML = `<p class="err">Couldn't reach the workspace service.</p>`; return; }
      if (h && h.error) { renderNone(h.error); return; }
      if (h && h.provisioned) renderReady(h); else renderNone();
    }
    function renderNone(err) {
      view.innerHTML =
        `<h2>Your dev box</h2>
         <p>Spin up a workspace seeded with the project's starter repo. Edit files in the
            <b>Files</b> app, or open the folder in your own editor or coding agent. Your
            commits are what gets reviewed.</p>
         ${err ? `<p class="err">${esc(err)}</p>` : ""}
         <div class="actions" style="justify-content:center">
           <button class="primary" id="create">Create workspace</button>
         </div>`;
      view.querySelector("#create").onclick = create;
    }
    function renderReady(h) {
      view.innerHTML =
        `<h2>Workspace ready</h2>
         <div class="card">
           <div class="row"><span class="k">Location</span><span class="v">${esc(h.workdir || "—")}</span></div>
           ${h.container ? `<div class="row"><span class="k">Container</span><span class="v">${esc(h.container)}</span></div>` : ""}
           ${h.connect_hint ? `<div class="muted">Connect a terminal:</div><div class="cmd">${esc(h.connect_hint)}</div>`
             : `<div class="muted">Open the folder above in your editor or coding agent, or edit in the Files app.</div>`}
           <div class="actions">
             <button class="primary" id="files">Open Files</button>
             <button id="recheck">Refresh</button>
             <button id="reset">Reset workspace</button>
           </div>
         </div>
         <p class="muted">Commit as you go — the grader reads your git history. Submit from the Submit app when done.</p>`;
      view.querySelector("#files").onclick = () => SimApps.open("files");
      view.querySelector("#recheck").onclick = refresh;
      view.querySelector("#reset").onclick = reset;
    }
    async function create() {
      view.innerHTML = `<p>Provisioning… first run may pull a container image.</p>`;
      let r;
      try { r = await (await api(`/environment/provision`, { method: "POST" })).json(); }
      catch (e) { renderNone("Provisioning failed — is the environment service up?"); return; }
      if (r.error) { renderNone(r.error); return; }
      renderReady(r);
    }
    async function reset() {
      await api(`/environment/teardown`, { method: "POST" });
      refresh();
    }

    if (wf.kind === "repo") repoView();
    else if (wf.kind === "doc") docView();
    else refresh();
    return { unmount() {} };
  }
});
