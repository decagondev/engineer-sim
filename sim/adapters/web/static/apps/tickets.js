SimApps.register({
  id: "tickets",
  title: "Tickets",
  accent: "#c56bff",
  icon: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M8 5v14" stroke-linejoin="round"/></svg>',
  css: `
  .tk{display:flex;flex-direction:column;height:100%;position:relative}
  .tk .top{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line);gap:12px}
  .tk .top h2{margin:0;font-size:15px}
  .tk .top .hint{font-size:12px;color:var(--muted)}
  .tk .top .new{margin-left:auto;background:var(--me);border:1px solid var(--me);color:#fff;font-weight:600;border-radius:9px;padding:7px 13px;font-size:13px;cursor:pointer}
  .tk .board{flex:1;display:flex;gap:12px;padding:14px;overflow:auto;min-height:0}
  .tk .col{flex:1;min-width:260px;display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line);border-radius:12px;min-height:0;transition:border-color .12s,background .12s}
  .tk .col.over{border-color:#3b6ef5;background:#182033}
  .tk .col .h{padding:10px 12px;font-size:12px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:center;letter-spacing:.02em}
  .tk .col .h .dot{width:8px;height:8px;border-radius:50%;flex:none}
  .tk .col.todo .dot{background:#8a93a4}
  .tk .col.doing .dot{background:#3b6ef5}
  .tk .col.done .dot{background:#37d67a}
  .tk .col .h .n{margin-left:auto;background:var(--panel-2);border-radius:9px;padding:1px 7px;font-size:11px}
  .tk .cards{flex:1;overflow-y:auto;padding:10px;display:flex;flex-direction:column;gap:8px;min-height:80px}
  .tk .card{background:var(--panel-2);border:1px solid var(--line);border-radius:10px;padding:10px 11px;cursor:grab;user-select:none}
  .tk .card:hover{border-color:#3a4353}
  .tk .card.dragging{opacity:.45;cursor:grabbing}
  .tk .card .meta{display:flex;align-items:center;gap:6px;margin-bottom:6px}
  .tk .card .key{font:11px/1 var(--mono);color:var(--faint);letter-spacing:.02em}
  .tk .type{width:14px;height:14px;flex:none;display:grid;place-items:center}
  .tk .pri{margin-left:auto;display:flex;align-items:center;font-size:11px;font-weight:700;letter-spacing:.02em}
  .tk .pri.highest,.tk .pri.high{color:#e0655c}
  .tk .pri.medium{color:#e0a94a}
  .tk .pri.low,.tk .pri.lowest{color:#5b9cff}
  .tk .card .t{font-size:13px;font-weight:600;line-height:1.35}
  .tk .card .d{font-size:12px;color:var(--muted);margin-top:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:normal}
  .tk .card .d.md p{margin:0}
  .tk .card .labs{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
  .tk .lab{font:10px/1.2 var(--mono);color:var(--muted);background:rgba(255,255,255,.05);border:1px solid var(--line);border-radius:999px;padding:2px 7px}
  .tk .card .foot{display:flex;align-items:center;gap:7px;margin-top:9px}
  .tk .av{width:20px;height:20px;border-radius:6px;display:grid;place-items:center;font-size:9px;font-weight:700;color:#0d0f13;flex:none}
  .tk .card .by{font-size:11px;color:var(--faint);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .tk .empty-col{margin:auto;color:var(--faint);font-size:12px;padding:18px 8px;text-align:center}
  .tk .overlay{position:absolute;inset:0;background:rgba(10,13,18,.62);display:flex;justify-content:flex-end;z-index:3}
  .tk .sheet{width:min(440px,100%);height:100%;background:var(--panel);border-left:1px solid var(--line);display:flex;flex-direction:column;box-shadow:-16px 0 40px rgba(0,0,0,.35)}
  .tk .sheet .sh{padding:14px 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px}
  .tk .sheet .sh .k{font:12px/1 var(--mono);color:var(--faint)}
  .tk .sheet .sh .x{margin-left:auto;background:transparent;border:1px solid var(--line);color:var(--text);border-radius:8px;padding:4px 10px;cursor:pointer}
  .tk .sheet .body{flex:1;overflow-y:auto;padding:16px 18px}
  .tk .sheet h3{margin:0 0 10px;font-size:17px;line-height:1.35}
  .tk .sheet .chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;align-items:center}
  .tk .sheet .desc.md{font-size:13.5px;color:var(--text)}
  .tk .sheet .who{margin-top:16px;display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
  .tk .form .box{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;width:min(460px,92%);margin:auto;display:flex;flex-direction:column;gap:10px}
  .tk .form h3{margin:0;font-size:15px}
  .tk .form input,.tk .form textarea,.tk .form select{background:var(--ink);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:10px 12px;font:inherit;outline:none}
  .tk .form textarea{min-height:120px;resize:vertical;font:13px/1.5 var(--ui)}
  .tk .form .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .tk .form label{font-size:11px;color:var(--muted);display:block;margin-bottom:4px}
  .tk .form .row{display:flex;gap:8px;justify-content:flex-end}
  .tk .form .save{background:var(--me);border:1px solid var(--me);color:#fff;font-weight:600;border-radius:9px;padding:9px 15px;cursor:pointer}
  .tk .form .cancel{background:var(--panel-2);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:9px 13px;cursor:pointer}
  `,
  mount(root, ctx) {
    root.innerHTML = `<div class="tk">
      <div class="top"><h2>Tickets</h2><span class="hint">Drag cards between columns</span>
        <button class="new">+ New ticket</button></div>
      <div class="board"></div></div>`;
    const app = root.querySelector(".tk"), q = s => app.querySelector(s);
    const sid = ctx.sid;
    const LABELS = { todo: "To Do", doing: "In Progress", done: "Done" };
    const TYPE_LABEL = { story: "Story", task: "Task", bug: "Bug", spike: "Spike" };
    const PRI_MARK = { highest: "↑↑", high: "↑", medium: "=", low: "↓", lowest: "↓↓" };
    const HUES = [210, 28, 150, 280, 340, 95];
    const hueFor = k => { let h = 0; for (const c of (k || "?")) h = (h * 31 + c.charCodeAt(0)) >>> 0; return HUES[h % HUES.length]; };
    const initials = n => (n || "?").split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
    function esc(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }
    function md(s) { return window.SimMD ? SimMD.render(s || "") : esc(s || "").replace(/\n/g, "<br>"); }
    function typeIcon(kind) {
      if (kind === "story") return `<svg class="type" viewBox="0 0 16 16"><path d="M4 2.5h6.2L13 5.2V13.5H4z" fill="#37d67a" stroke="none"/><path d="M10.1 2.5V5.3H13" fill="none" stroke="#0d1015" stroke-width="1.2"/></svg>`;
      if (kind === "bug") return `<svg class="type" viewBox="0 0 16 16"><circle cx="8" cy="8" r="5.2" fill="#e0655c"/></svg>`;
      if (kind === "spike") return `<svg class="type" viewBox="0 0 16 16"><path d="M8 2.4l5.2 11.2H2.8z" fill="#c56bff"/></svg>`;
      return `<svg class="type" viewBox="0 0 16 16"><rect x="3.2" y="3.2" width="9.6" height="9.6" rx="2" fill="#3b6ef5"/></svg>`;
    }

    let boardData = { columns: [] }, dragging = false;

    async function load() {
      boardData = await (await fetch(`/api/session/${sid}/tickets`)).json();
      render(boardData.columns || []);
    }
    async function move(id, status) {
      const cur = findTicket(id);
      if (!cur || cur.status === status) return;
      boardData = await (await fetch(`/api/session/${sid}/tickets/${id}/move`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status })
      })).json();
      render(boardData.columns || []);
    }
    function findTicket(id) {
      for (const c of boardData.columns || []) {
        const t = (c.tickets || []).find(x => x.id === id);
        if (t) return t;
      }
      return null;
    }
    function avatar(name, key) {
      return `<span class="av" style="background:hsl(${hueFor(key || name)} 55% 62%)">${esc(initials(name))}</span>`;
    }
    function render(columns) {
      const board = q(".board"); board.innerHTML = "";
      columns.forEach(col => {
        const el = document.createElement("div");
        el.className = "col " + col.status;
        el.innerHTML = `<div class="h"><span class="dot"></span>${LABELS[col.status] || col.status}` +
          `<span class="n">${col.tickets.length}</span></div><div class="cards"></div>`;
        const cards = el.querySelector(".cards");
        if (!col.tickets.length) {
          const z = document.createElement("div"); z.className = "empty-col";
          z.textContent = "Drop tickets here";
          cards.appendChild(z);
        }
        col.tickets.forEach(t => cards.appendChild(card(t)));
        bindDrop(el, col.status);
        board.appendChild(el);
      });
    }
    function bindDrop(el, status) {
      const on = ev => { ev.preventDefault(); el.classList.add("over"); };
      el.addEventListener("dragover", on);
      el.addEventListener("dragenter", on);
      el.addEventListener("dragleave", ev => {
        if (!el.contains(ev.relatedTarget)) el.classList.remove("over");
      });
      el.addEventListener("drop", ev => {
        ev.preventDefault(); el.classList.remove("over");
        const id = ev.dataTransfer.getData("text/ticket-id");
        if (id) move(id, status);
      });
    }
    function card(t) {
      const el = document.createElement("div");
      el.className = "card"; el.draggable = true;
      el.dataset.id = t.id;
      const excerpt = (t.description || "").replace(/^#+\s+/gm, "").replace(/\n+/g, " ").trim();
      el.innerHTML =
        `<div class="meta">${typeIcon(t.issue_type)}<span class="key">${esc(t.key || t.id)}</span>` +
          `<span class="pri ${esc(t.priority || "medium")}" title="${esc(t.priority)}">${PRI_MARK[t.priority] || "="}</span></div>` +
        `<div class="t">${esc(t.title)}</div>` +
        (excerpt ? `<div class="d">${esc(excerpt)}</div>` : "") +
        ((t.labels || []).length ? `<div class="labs">${t.labels.map(l => `<span class="lab">${esc(l)}</span>`).join("")}</div>` : "") +
        `<div class="foot">${avatar(t.by_name, t.created_by)}<span class="by">${esc(t.by_name)}</span></div>`;
      el.addEventListener("dragstart", ev => {
        dragging = true;
        el.classList.add("dragging");
        ev.dataTransfer.setData("text/ticket-id", t.id);
        ev.dataTransfer.effectAllowed = "move";
      });
      el.addEventListener("dragend", () => { el.classList.remove("dragging"); setTimeout(() => { dragging = false; }, 40); });
      el.addEventListener("click", () => { if (!dragging) openDetail(t); });
      return el;
    }
    function openDetail(t) {
      const f = document.createElement("div"); f.className = "overlay";
      f.innerHTML = `<div class="sheet">
        <div class="sh">${typeIcon(t.issue_type)}<span class="k">${esc(t.key || t.id)}</span>
          <span class="pri ${esc(t.priority || "medium")}">${esc((t.priority || "medium").toUpperCase())}</span>
          <button class="x">Close</button></div>
        <div class="body">
          <h3>${esc(t.title)}</h3>
          <div class="chips">
            <span class="lab">${esc(TYPE_LABEL[t.issue_type] || t.issue_type || "Task")}</span>
            <span class="lab">${esc(LABELS[t.status] || t.status)}</span>
            ${(t.labels || []).map(l => `<span class="lab">${esc(l)}</span>`).join("")}
          </div>
          <div class="desc md">${t.description ? md(t.description) : "<p style='color:var(--muted)'>No description.</p>"}</div>
          <div class="who">${avatar(t.by_name, t.created_by)} Reporter · ${esc(t.by_name)}</div>
        </div>
      </div>`;
      f.querySelector(".x").onclick = () => f.remove();
      f.addEventListener("click", ev => { if (ev.target === f) f.remove(); });
      app.appendChild(f);
    }
    function openForm() {
      const f = document.createElement("div"); f.className = "overlay form";
      f.innerHTML = `<div class="box">
        <h3>Create ticket</h3>
        <input class="ti" placeholder="Summary"/>
        <textarea class="de" placeholder="Description — context, acceptance criteria, notes…"></textarea>
        <div class="grid">
          <div><label>Type</label>
            <select class="ty"><option value="story">Story</option><option value="task" selected>Task</option>
              <option value="bug">Bug</option><option value="spike">Spike</option></select></div>
          <div><label>Priority</label>
            <select class="pr"><option value="highest">Highest</option><option value="high">High</option>
              <option value="medium" selected>Medium</option><option value="low">Low</option>
              <option value="lowest">Lowest</option></select></div>
        </div>
        <div><label>Labels</label><input class="lb" placeholder="discovery, cs, mvp"/></div>
        <div class="row"><button class="cancel">Cancel</button><button class="save">Create</button></div>
      </div>`;
      app.appendChild(f);
      f.querySelector(".ti").focus();
      f.querySelector(".cancel").onclick = () => f.remove();
      f.addEventListener("click", ev => { if (ev.target === f) f.remove(); });
      f.querySelector(".save").onclick = async () => {
        const title = f.querySelector(".ti").value.trim(); if (!title) return;
        await fetch(`/api/session/${sid}/tickets`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title,
            description: f.querySelector(".de").value.trim(),
            issue_type: f.querySelector(".ty").value,
            priority: f.querySelector(".pr").value,
            labels: f.querySelector(".lb").value,
          })
        });
        f.remove(); load();
      };
    }
    q(".new").onclick = openForm;
    load();
    return { unmount() {} };
  }
});
