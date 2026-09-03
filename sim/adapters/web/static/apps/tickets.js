SimApps.register({
  id: "tickets",
  title: "Tickets",
  accent: "#c56bff",
  icon: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M8 5v14" stroke-linejoin="round"/></svg>',
  css: `
  .tk{display:flex;flex-direction:column;height:100%}
  .tk .top{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line)}
  .tk .top h2{margin:0;font-size:15px}
  .tk .top .new{margin-left:auto;background:var(--me);border:1px solid var(--me);color:#fff;font-weight:600;border-radius:9px;padding:7px 13px;font-size:13px;cursor:pointer}
  .tk .board{flex:1;display:flex;gap:14px;padding:16px;overflow-x:auto;min-height:0}
  .tk .col{flex:1;min-width:230px;display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
  .tk .col .h{padding:10px 13px;font-size:12px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:center}
  .tk .col .h .n{margin-left:auto;background:var(--panel-2);border-radius:9px;padding:1px 7px;font-size:11px}
  .tk .cards{flex:1;overflow-y:auto;padding:10px;display:flex;flex-direction:column;gap:9px}
  .tk .card{background:var(--panel-2);border:1px solid var(--line);border-radius:10px;padding:11px 12px}
  .tk .card .t{font-size:13px;font-weight:600}
  .tk .card .d{font-size:12px;color:var(--muted);margin-top:4px;white-space:pre-wrap}
  .tk .card .foot{display:flex;align-items:center;gap:6px;margin-top:9px}
  .tk .card .by{font-size:11px;color:var(--faint)}
  .tk .card .mv{margin-left:auto;display:flex;gap:5px}
  .tk .card .mv button{background:var(--ink);border:1px solid var(--line);color:var(--text);border-radius:7px;padding:3px 8px;font-size:12px;cursor:pointer}
  .tk .card .mv button:hover{border-color:var(--me)}
  .tk .form{position:absolute;inset:0;background:rgba(10,13,18,.6);display:flex;align-items:center;justify-content:center}
  .tk .form .box{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;width:min(440px,90%);display:flex;flex-direction:column;gap:10px}
  .tk .form input,.tk .form textarea{background:var(--ink);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:10px 12px;font:inherit;outline:none}
  .tk .form textarea{min-height:90px;resize:vertical}
  .tk .form .row{display:flex;gap:8px;justify-content:flex-end}
  .tk .form .row .save{background:var(--me);border:1px solid var(--me);color:#fff;font-weight:600;border-radius:9px;padding:9px 15px;cursor:pointer}
  .tk .form .row .cancel{background:var(--panel-2);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:9px 13px;cursor:pointer}
  `,
  mount(root, ctx) {
    root.innerHTML = `<div class="tk" style="position:relative">
      <div class="top"><h2>Tickets</h2><button class="new">New ticket</button></div>
      <div class="board"></div></div>`;
    const app = root.querySelector(".tk"), q = s => app.querySelector(s);
    const sid = ctx.sid;
    const LABELS = { todo: "To Do", doing: "In Progress", done: "Done" };
    const NEXT = { todo: "doing", doing: "done", done: null };
    const PREV = { todo: null, doing: "todo", done: "doing" };
    function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

    async function load() {
      const b = await (await fetch(`/api/session/${sid}/tickets`)).json();
      render(b.columns || []);
    }
    function render(columns) {
      const board = q(".board"); board.innerHTML = "";
      columns.forEach(col => {
        const el = document.createElement("div"); el.className = "col";
        el.innerHTML = `<div class="h">${LABELS[col.status] || col.status}<span class="n">${col.tickets.length}</span></div><div class="cards"></div>`;
        const cards = el.querySelector(".cards");
        col.tickets.forEach(t => cards.appendChild(card(t)));
        board.appendChild(el);
      });
    }
    function card(t) {
      const el = document.createElement("div"); el.className = "card";
      const back = PREV[t.status], fwd = NEXT[t.status];
      el.innerHTML =
        `<div class="t">${esc(t.title)}</div>` +
        (t.description ? `<div class="d">${esc(t.description)}</div>` : "") +
        `<div class="foot"><span class="by">${t.by_name}</span><span class="mv">` +
        (back ? `<button data-mv="${back}">←</button>` : "") +
        (fwd ? `<button data-mv="${fwd}">→</button>` : "") +
        `</span></div>`;
      el.querySelectorAll("[data-mv]").forEach(b => b.onclick = async () => {
        await fetch(`/api/session/${sid}/tickets/${t.id}/move`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: b.dataset.mv }) });
        load();
      });
      return el;
    }
    function openForm() {
      const f = document.createElement("div"); f.className = "form";
      f.innerHTML = `<div class="box">
        <input class="ti" placeholder="Ticket title"/>
        <textarea class="de" placeholder="Description (optional)"></textarea>
        <div class="row"><button class="cancel">Cancel</button><button class="save">Create</button></div></div>`;
      app.appendChild(f);
      f.querySelector(".ti").focus();
      f.querySelector(".cancel").onclick = () => f.remove();
      f.querySelector(".save").onclick = async () => {
        const title = f.querySelector(".ti").value.trim(); if (!title) return;
        await fetch(`/api/session/${sid}/tickets`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, description: f.querySelector(".de").value.trim() }) });
        f.remove(); load();
      };
    }
    q(".new").onclick = openForm;
    load();
    return { unmount() {} };
  }
});
