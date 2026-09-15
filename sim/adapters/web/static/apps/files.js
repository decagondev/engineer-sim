SimApps.register({
  id: "files",
  title: "Files",
  accent: "#8a93a4",
  icon: '<svg viewBox="0 0 24 24"><path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" stroke-linejoin="round"/></svg>',
  css: `
  .files{display:flex;flex-direction:column;height:100%}
  .files .bar{display:flex;align-items:center;gap:6px;padding:8px 12px;border-bottom:1px solid var(--line);font:12.5px/1 var(--mono);color:var(--muted);flex-wrap:wrap;min-height:38px}
  .files .bar a{color:var(--me);cursor:pointer}
  .files .bar .sep{color:var(--faint)}
  .files .bar .sp{flex:1}
  .files .bar .rev{color:var(--faint);font-size:11.5px}
  .files .bar .mode{font-size:10.5px;border:1px solid var(--line);border-radius:999px;padding:3px 8px;color:var(--muted)}
  .files .bar .mode.ro{color:var(--sig);border-color:var(--sig-line);background:var(--sig-bg)}
  .files button{border-radius:8px;padding:6px 11px;font:inherit;font-size:12.5px;cursor:pointer;border:1px solid var(--line);background:var(--panel-2);color:var(--text)}
  .files button.primary{background:var(--me);border-color:var(--me);color:#fff;font-weight:600}
  .files button:disabled{opacity:.45;cursor:default}
  .files .body{flex:1;display:flex;min-height:0}
  .files .listing{width:240px;flex:none;border-right:1px solid var(--line);overflow-y:auto;background:var(--panel)}
  .files .item{display:flex;align-items:center;gap:9px;padding:7px 12px;cursor:pointer;font-size:13px;white-space:nowrap}
  .files .item:hover{background:var(--panel-2)}
  .files .item.open{background:rgba(59,110,245,.14)}
  .files .item .ic{width:16px;text-align:center;color:var(--muted);flex:none}
  .files .item .nm{overflow:hidden;text-overflow:ellipsis}
  .files .item .sz{margin-left:auto;font:11px/1 var(--mono);color:var(--faint)}
  .files .pane{flex:1;min-width:0;display:flex;flex-direction:column;background:var(--ink)}
  .files .tabs{display:flex;align-items:stretch;border-bottom:1px solid var(--line);background:var(--panel);overflow-x:auto;min-height:34px}
  .files .tab{display:flex;align-items:center;gap:7px;padding:0 12px;font:12.5px var(--mono);color:var(--muted);cursor:pointer;border-right:1px solid var(--line);white-space:nowrap}
  .files .tab.active{color:var(--text);background:var(--ink);box-shadow:inset 0 -2px 0 var(--me)}
  .files .tab .dot{width:7px;height:7px;border-radius:50%;background:var(--sig);display:none}
  .files .tab.dirty .dot{display:block}
  .files .tab .x{color:var(--faint);padding:0 2px;border-radius:4px}
  .files .tab .x:hover{color:var(--text);background:var(--panel-2)}
  .files .edwrap{flex:1;position:relative;min-height:0}
  .files .preview{position:absolute;inset:0;overflow:auto;padding:18px 24px;background:var(--ink);display:none}
  .files .preview.on{display:block}
  .files .status{display:flex;align-items:center;gap:10px;padding:6px 12px;border-top:1px solid var(--line);font:11.5px var(--mono);color:var(--muted);background:var(--panel)}
  .files .status .sp{flex:1}
  .files .status .ok{color:var(--ok,#37d67a)}
  .files .status .bad{color:#e5807a}
  .files .note{padding:20px;color:var(--muted);font-size:13px}
  .files .empty{margin:auto;color:var(--muted);text-align:center;padding:28px;max-width:420px;line-height:1.6}
  .files .empty button{margin-top:10px}
  `,
  mount(root, ctx) {
    root.innerHTML = `<div class="files">
      <div class="bar"></div>
      <div class="body">
        <div class="listing"></div>
        <div class="pane">
          <div class="tabs"></div>
          <div class="edwrap"><div class="note">Select a file to open it.</div><div class="preview"></div></div>
          <div class="status"><span class="msg"></span><span class="sp"></span>
            <button class="pv" hidden>Preview</button><button class="primary save" hidden>Save</button></div>
        </div>
      </div></div>`;
    const app = root.querySelector(".files"), q = s => app.querySelector(s);
    const sid = ctx.sid;
    const wf = (ctx.scenario && ctx.scenario.workflow) || { kind: "sandbox", editable: true };
    const bar = q(".bar"), listing = q(".listing"), tabsEl = q(".tabs"), edwrap = q(".edwrap"),
          preview = q(".preview"), msg = q(".msg"), saveBtn = q(".save"), pvBtn = q(".pv");
    let cwd = "", entries = [], editor = null, revision = "";
    const tabs = new Map();            // path -> { text, saved, dirty }
    let active = null, previewOn = false, timer = null, dead = false;

    const esc = s => { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; };
    const join = (a, b) => a ? a + "/" + b : b;
    const fmtSize = n => n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(1) + " K" : (n / 1048576).toFixed(1) + " M";
    const api = (p, o) => fetch(`/api/session/${sid}${p}`, o);
    const say = (t, cls) => { msg.textContent = t; msg.className = "msg " + (cls || ""); };

    // ---- directory listing ------------------------------------------------
    async function nav(path, { keepMsg } = {}) {
      const r = await api(`/files/list?path=${encodeURIComponent(path)}`);
      if (r.status === 409 || r.status === 501 || r.status === 503) { showNoWorkspace((await r.json()).error, r.status); return false; }
      const data = await r.json();
      if (data.error) { listing.innerHTML = `<div class="note">${esc(data.error)}</div>`; return false; }
      cwd = path; entries = data.entries;
      if (typeof data.editable === "boolean") wf.editable = data.editable;
      renderBar(); renderList();
      if (!keepMsg) say("");
      return true;
    }
    function renderBar() {
      const parts = cwd ? cwd.split("/") : [];
      let acc = "", html = `<a data-p="">workspace</a>`;
      parts.forEach(seg => { acc = join(acc, seg); html += ` <span class="sep">/</span> <a data-p="${esc(acc)}">${esc(seg)}</a>`; });
      html += `<span class="sp"></span>` +
        (revision ? `<span class="rev">@ ${esc(revision)}</span>` : "") +
        `<span class="mode ${wf.editable ? "" : "ro"}">${wf.editable ? "editable" : "read-only · push to update"}</span>` +
        `<button class="refresh" title="Re-read the workspace">Refresh</button>`;
      bar.innerHTML = html;
      bar.querySelectorAll("a").forEach(a => a.onclick = () => nav(a.dataset.p));
      bar.querySelector(".refresh").onclick = refresh;
    }
    function renderList() {
      listing.innerHTML = "";
      if (cwd) {
        const up = document.createElement("div"); up.className = "item";
        up.innerHTML = `<span class="ic">↩</span><span class="nm">..</span>`;
        up.onclick = () => nav(cwd.split("/").slice(0, -1).join("/"));
        listing.appendChild(up);
      }
      entries.forEach(e => {
        const p = join(cwd, e.name);
        const it = document.createElement("div"); it.className = "item" + (tabs.has(p) ? " open" : "");
        it.innerHTML = `<span class="ic">${e.is_dir ? "📁" : "📄"}</span><span class="nm">${esc(e.name)}</span>` +
          (e.is_dir ? "" : `<span class="sz">${fmtSize(e.size)}</span>`);
        it.onclick = () => e.is_dir ? nav(p) : openFile(p);
        listing.appendChild(it);
      });
    }
    async function refresh() {
      say("Refreshing…");
      try {
        const r = await (await api(`/files/refresh`, { method: "POST" })).json();
        if (r.error) { say(r.error, "bad"); return; }
        revision = r.revision || "";
      } catch (e) { say("Refresh failed.", "bad"); return; }
      const ok = await nav(cwd, { keepMsg: true });
      if (!ok) return;
      // re-read open files that are not dirty so a push shows up in the editor
      for (const [p, t] of tabs) {
        if (t.dirty) continue;
        const c = await (await api(`/files/read?path=${encodeURIComponent(p)}`)).json();
        if (c.text != null) { t.text = t.saved = c.text; if (p === active && editor) editor.setValue(c.text); }
      }
      say("Up to date" + (revision ? " @ " + revision : ""), "ok");
    }

    // ---- tabs + editor ----------------------------------------------------
    async function openFile(path) {
      if (!tabs.has(path)) {
        const c = await (await api(`/files/read?path=${encodeURIComponent(path)}`)).json();
        if (c.error) { say(c.error, "bad"); return; }
        if (c.text == null) { say(c.note || "cannot preview this file", "bad"); return; }
        tabs.set(path, { text: c.text, saved: c.text, dirty: false });
      }
      activate(path);
      renderList();
    }
    function activate(path) {
      if (active && editor && tabs.has(active)) tabs.get(active).text = editor.getValue();
      active = path;
      const t = tabs.get(path);
      if (!editor) {
        edwrap.querySelector(".note") && edwrap.querySelector(".note").remove();
        editor = SimEditor.mount(edwrap, {
          path, text: t.text, readOnly: !wf.editable,
          onSave: save,
          onChange: () => { if (!active) return; const tt = tabs.get(active); if (!tt) return;
            const v = editor.getValue(); tt.text = v; const d = v !== tt.saved;
            if (d !== tt.dirty) { tt.dirty = d; renderTabs(); } },
        });
        saveBtn.hidden = !wf.editable; pvBtn.hidden = false;
      } else { editor.setPath(path); editor.setValue(t.text); }
      if (previewOn) renderPreview();
      renderTabs(); editor.focus();
    }
    function renderTabs() {
      tabsEl.innerHTML = "";
      for (const [p, t] of tabs) {
        const el = document.createElement("div");
        el.className = "tab" + (p === active ? " active" : "") + (t.dirty ? " dirty" : "");
        el.innerHTML = `<span class="dot"></span><span>${esc(p.split("/").pop())}</span><span class="x" title="Close">×</span>`;
        el.onclick = e => { if (e.target.classList.contains("x")) closeTab(p); else activate(p); };
        el.title = p;
        tabsEl.appendChild(el);
      }
      pvBtn.textContent = previewOn ? "Editor" : "Preview";
      pvBtn.hidden = !(active && /\.(md|markdown)$/i.test(active));
      saveBtn.disabled = !(active && tabs.get(active) && tabs.get(active).dirty);
    }
    async function closeTab(p) {
      const t = tabs.get(p);
      if (t && t.dirty && wf.editable) await save(p);
      tabs.delete(p);
      if (active === p) { active = null; const next = [...tabs.keys()].pop(); if (next) activate(next); else { editor && editor.setValue(""); } }
      renderTabs(); renderList();
    }
    async function save(path) {
      const p = (typeof path === "string" && path) || active;
      if (!p || !wf.editable) return;
      const t = tabs.get(p); if (!t) return;
      if (p === active && editor) t.text = editor.getValue();
      if (!t.dirty) { say("Nothing to save.", ""); return; }
      say("Saving…");
      try {
        const r = await (await api(`/files/write`, { method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: p, text: t.text }) })).json();
        if (r.error) { say(r.error, "bad"); return; }
        t.saved = t.text; t.dirty = false; revision = r.revision || revision;
        say(`Saved ${p.split("/").pop()}`, "ok"); renderTabs(); renderBar();
      } catch (e) { say("Save failed — check your connection.", "bad"); }
    }
    async function saveAllDirty() {
      for (const [p, t] of tabs) if (t.dirty) await save(p);
    }
    function renderPreview() {
      const t = active && tabs.get(active);
      preview.innerHTML = t && window.SimMD ? SimMD.render(t.text) : "";
      if (window.SimMD) SimMD.hydrate(preview);
    }
    pvBtn.onclick = () => {
      previewOn = !previewOn;
      if (previewOn) { if (active && editor) tabs.get(active).text = editor.getValue(); renderPreview(); }
      preview.classList.toggle("on", previewOn); renderTabs();
      if (!previewOn && editor) editor.focus();
    };
    saveBtn.onclick = () => save();

    function showNoWorkspace(err, status) {
      const body = app.querySelector(".body");
      const target = wf.kind === "repo" ? "workspace" : "workspace";
      const copy = wf.kind === "repo"
        ? `No repo linked yet.<br/>Open the <b>Workspace</b> app, paste your public GitHub repo URL, then come back.`
        : status === 503 ? `Your workspace could not be created.<br/><span style="color:#e5807a">${esc(err || "")}</span>`
        : `No workspace yet.<br/>Open the <b>Workspace</b> app to create your dev box, then come back.`;
      body.innerHTML = `<div class="empty">${copy}<br/><button class="primary" id="tows">Open Workspace</button></div>`;
      body.querySelector("#tows").onclick = () => SimApps.open(target);
    }

    // autosave dirty tabs every 20s in editable workspaces (design docs are precious)
    if (wf.editable) timer = setInterval(() => { if (!dead) saveAllDirty(); }, 20000);

    (async () => {
      const ok = await nav("");
      if (ok && wf.kind === "doc" && entries.some(e => e.name === "DESIGN.md")) openFile("DESIGN.md");
    })();
    return { unmount() { dead = true; if (timer) clearInterval(timer); if (wf.editable) saveAllDirty(); if (editor) editor.destroy(); } };
  }
});
