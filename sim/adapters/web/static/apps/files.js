SimApps.register({
  id: "files",
  title: "Files",
  accent: "#8a93a4",
  icon: '<svg viewBox="0 0 24 24"><path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" stroke-linejoin="round"/></svg>',
  css: `
  .files{display:flex;flex-direction:column;height:100%}
  .files .bar{display:flex;align-items:center;gap:6px;padding:10px 14px;border-bottom:1px solid var(--line);font:12.5px/1 var(--mono);color:var(--muted);flex-wrap:wrap}
  .files .bar a{color:var(--me);cursor:pointer}
  .files .bar .sep{color:var(--faint)}
  .files .body{flex:1;display:flex;min-height:0}
  .files .listing{width:260px;flex:none;border-right:1px solid var(--line);overflow-y:auto;background:var(--panel)}
  .files .item{display:flex;align-items:center;gap:9px;padding:8px 14px;cursor:pointer;font-size:13px}
  .files .item:hover{background:var(--panel-2)}
  .files .item .ic{width:16px;text-align:center;color:var(--muted)}
  .files .item .sz{margin-left:auto;font:11px/1 var(--mono);color:var(--faint)}
  .files .viewer{flex:1;min-width:0;overflow:auto;background:var(--ink)}
  .files .viewer pre{margin:0;padding:16px 18px;font:12.5px/1.6 var(--mono);color:var(--text);white-space:pre;tab-size:2}
  .files .viewer .note{padding:20px;color:var(--muted);font-size:13px}
  .files .empty{margin:auto;color:var(--muted);text-align:center;padding:28px}
  .files .empty button{margin-top:10px;background:var(--me);border:1px solid var(--me);color:#fff;border-radius:9px;padding:8px 14px;font:inherit;font-size:13px;cursor:pointer}
  `,
  mount(root, ctx) {
    root.innerHTML = `<div class="files"><div class="bar"></div><div class="body">
      <div class="listing"></div><div class="viewer"><div class="note">Select a file to view it.</div></div></div></div>`;
    const app = root.querySelector(".files"), q = s => app.querySelector(s);
    const sid = ctx.sid;
    const bar = q(".bar"), listing = q(".listing"), viewer = q(".viewer");
    let cwd = "";

    function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
    function join(a, b) { return a ? a + "/" + b : b; }
    function fmtSize(n) { return n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(1) + " K" : (n / 1048576).toFixed(1) + " M"; }

    async function nav(path) {
      const r = await fetch(`/api/session/${sid}/files/list?path=${encodeURIComponent(path)}`);
      if (r.status === 409) { showNoWorkspace(); return; }
      const data = await r.json();
      if (data.error) { listing.innerHTML = `<div class="note" style="padding:14px">${data.error}</div>`; return; }
      cwd = path; renderBar(); renderList(data.entries);
    }
    function renderBar() {
      const parts = cwd ? cwd.split("/") : [];
      let acc = "";
      let html = `<a data-p="">workspace</a>`;
      parts.forEach(seg => { acc = join(acc, seg); html += ` <span class="sep">/</span> <a data-p="${acc}">${esc(seg)}</a>`; });
      bar.innerHTML = html;
      bar.querySelectorAll("a").forEach(a => a.onclick = () => nav(a.dataset.p));
    }
    function renderList(entries) {
      listing.innerHTML = "";
      if (cwd) {
        const up = document.createElement("div"); up.className = "item";
        up.innerHTML = `<span class="ic">↩</span><span>..</span>`;
        up.onclick = () => nav(cwd.split("/").slice(0, -1).join("/"));
        listing.appendChild(up);
      }
      entries.forEach(e => {
        const it = document.createElement("div"); it.className = "item";
        it.innerHTML = `<span class="ic">${e.is_dir ? "📁" : "📄"}</span><span>${esc(e.name)}</span>` +
          (e.is_dir ? "" : `<span class="sz">${fmtSize(e.size)}</span>`);
        it.onclick = () => e.is_dir ? nav(join(cwd, e.name)) : openFile(join(cwd, e.name));
        listing.appendChild(it);
      });
    }
    async function openFile(path) {
      viewer.innerHTML = `<div class="note">Loading…</div>`;
      const c = await (await fetch(`/api/session/${sid}/files/read?path=${encodeURIComponent(path)}`)).json();
      if (c.error) { viewer.innerHTML = `<div class="note">${c.error}</div>`; return; }
      if (c.text == null) { viewer.innerHTML = `<div class="note">${c.note || "cannot preview"}</div>`; return; }
      viewer.innerHTML = `<pre>${esc(c.text)}</pre>`;
    }
    function showNoWorkspace() {
      app.querySelector(".body").innerHTML =
        `<div class="empty">No workspace yet.<br/>Open the <b>Workspace</b> app to create your dev box, then come back.<br/><button id="tows">Open Workspace</button></div>`;
      app.querySelector("#tows").onclick = () => SimApps.open("workspace");
    }

    nav("");
    return { unmount() {} };
  }
});
