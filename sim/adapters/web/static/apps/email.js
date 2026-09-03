SimApps.register({
  id: "email",
  title: "Mail",
  accent: "#caa24a",
  icon: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M4 7l8 6 8-6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  css: `
  .mail{display:flex;height:100%}
  .mail .list{width:280px;flex:none;border-right:1px solid var(--line);display:flex;flex-direction:column;background:var(--panel)}
  .mail .list .head{padding:12px 14px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:8px}
  .mail .list .head .t{font-size:13px;color:var(--muted);flex:1}
  .mail .compose-btn{background:var(--me);border:1px solid var(--me);color:#fff;border-radius:8px;padding:6px 11px;font-size:13px;font-weight:600;cursor:pointer}
  .mail .threads{flex:1;overflow-y:auto}
  .mail .thread{padding:11px 14px;border-bottom:1px solid var(--line);cursor:pointer;position:relative}
  .mail .thread:hover,.mail .thread.active{background:var(--panel-2)}
  .mail .thread .from{font-size:13px;font-weight:600;display:flex;align-items:center;gap:6px}
  .mail .thread .subj{font-size:13px;margin-top:1px}
  .mail .thread .prev{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
  .mail .thread .dot{width:7px;height:7px;border-radius:50%;background:var(--sig);flex:none}
  .mail .reader{flex:1;display:flex;flex-direction:column;min-width:0}
  .mail .reader .empty{margin:auto;color:var(--muted);text-align:center;padding:24px}
  .mail .rhead{padding:14px 18px;border-bottom:1px solid var(--line)}
  .mail .rhead .s{font-size:16px;font-weight:600}
  .mail .rhead .w{font-size:13px;color:var(--muted);margin-top:2px}
  .mail .emails{flex:1;overflow-y:auto;padding:8px 18px}
  .mail .email{padding:14px 0;border-bottom:1px solid var(--line)}
  .mail .email .meta{font-size:12px;color:var(--muted);margin-bottom:6px;display:flex;gap:8px}
  .mail .email .meta .n{color:var(--text);font-weight:600}
  .mail .email .meta .t{font-family:var(--mono);color:var(--faint)}
  .mail .email .body{white-space:pre-wrap;font-size:14px;line-height:1.55}
  .mail .replybar{border-top:1px solid var(--line);padding:12px 18px;display:flex;flex-direction:column;gap:8px}
  .mail .replybar textarea{background:var(--panel);border:1px solid var(--line);color:var(--text);border-radius:10px;padding:10px 12px;font:inherit;resize:vertical;min-height:64px;outline:none}
  .mail .replybar textarea:focus{border-color:var(--me)}
  .mail .replybar .send{align-self:flex-end;background:var(--me);border:1px solid var(--me);color:#fff;font-weight:600;border-radius:9px;padding:8px 16px;cursor:pointer}
  .mail .composeform{padding:18px;display:flex;flex-direction:column;gap:10px;overflow-y:auto}
  .mail .composeform label{font-size:12px;color:var(--muted)}
  .mail .composeform select,.mail .composeform input,.mail .composeform textarea{background:var(--panel);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:10px 12px;font:inherit;outline:none}
  .mail .composeform textarea{min-height:160px;resize:vertical}
  .mail .composeform .actions{display:flex;gap:8px;justify-content:flex-end}
  .mail .composeform .send{background:var(--me);border:1px solid var(--me);color:#fff;font-weight:600;border-radius:9px;padding:9px 16px;cursor:pointer}
  .mail .composeform .cancel{background:var(--panel-2);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:9px 14px;cursor:pointer}
  .mail .busy{margin:auto;color:var(--muted)}
  `,
  mount(root, ctx) {
    root.innerHTML = `<div class="mail">
      <div class="list">
        <div class="head"><span class="t">Inbox</span><button class="compose-btn">Compose</button></div>
        <div class="threads"></div>
      </div>
      <div class="reader"><div class="empty">Select a conversation, or compose a new email.</div></div>
    </div>`;
    const app = root.querySelector(".mail"), q = s => app.querySelector(s);
    const sid = ctx.sid, personas = (ctx.scenario.personas || []);
    const nameOf = k => (personas.find(p => p.key === k) || {}).name || k;
    const threadsEl = q(".threads"), reader = q(".reader");
    let activeId = null;

    const fmt = ts => { const d = new Date(ts); return isNaN(d) ? "" : d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); };

    async function loadThreads() {
      const data = await (await fetch(`/api/session/${sid}/mail/threads`)).json();
      renderThreads(data.threads || []);
    }
    function renderThreads(list) {
      threadsEl.innerHTML = "";
      if (list.length === 0) { threadsEl.innerHTML = `<div style="padding:16px;color:var(--muted);font-size:13px">No mail yet.</div>`; return; }
      list.forEach(t => {
        const unread = t.last_from && t.last_from !== "tester" && t.id !== activeId;
        const row = document.createElement("div");
        row.className = "thread" + (t.id === activeId ? " active" : "");
        row.innerHTML =
          `<div class="from">${unread ? '<span class="dot"></span>' : ''}${t.with_name}</div>` +
          `<div class="subj">${t.subject}</div>` +
          `<div class="prev">${t.preview || ""}</div>`;
        row.onclick = () => openThread(t.id);
        threadsEl.appendChild(row);
      });
    }

    async function openThread(id) {
      activeId = id;
      reader.innerHTML = `<div class="busy">Loading…</div>`;
      const t = await (await fetch(`/api/session/${sid}/mail/thread/${id}`)).json();
      renderThread(t);
      loadThreads();
    }
    function renderThread(t) {
      reader.innerHTML =
        `<div class="rhead"><div class="s">${t.subject}</div><div class="w">with ${t.with_name}</div></div>` +
        `<div class="emails"></div>` +
        `<div class="replybar"><textarea placeholder="Write a reply…"></textarea><button class="send">Send reply</button></div>`;
      const box = reader.querySelector(".emails");
      t.emails.forEach(e => {
        const d = document.createElement("div"); d.className = "email";
        d.innerHTML = `<div class="meta"><span class="n">${e.sender_name}</span><span class="t">${fmt(e.ts)}</span></div><div class="body">${escapeHtml(e.body)}</div>`;
        box.appendChild(d);
      });
      box.scrollTop = box.scrollHeight;
      const ta = reader.querySelector("textarea"), btn = reader.querySelector(".send");
      btn.onclick = async () => {
        const body = ta.value.trim(); if (!body) return;
        btn.disabled = true; btn.textContent = "Sending…";
        const upd = await (await fetch(`/api/session/${sid}/mail/thread/${t.id}/reply`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body }) })).json();
        renderThread(upd); loadThreads();
      };
    }

    function compose() {
      activeId = null; renderThreads([]);  // clear active highlight
      loadThreads();
      const opts = personas.map(p => `<option value="${p.key}">${p.name} — ${p.role}</option>`).join("");
      reader.innerHTML =
        `<div class="composeform">
           <div><label>To</label><br/><select class="to" style="width:100%">${opts}</select></div>
           <div><label>Subject</label><br/><input class="subj" style="width:100%" placeholder="Subject"/></div>
           <textarea class="body" placeholder="Write your email…"></textarea>
           <div class="actions"><button class="cancel">Cancel</button><button class="send">Send email</button></div>
         </div>`;
      reader.querySelector(".cancel").onclick = () => { reader.innerHTML = `<div class="empty">Select a conversation, or compose a new email.</div>`; };
      reader.querySelector(".send").onclick = async () => {
        const to = reader.querySelector(".to").value;
        const subject = reader.querySelector(".subj").value.trim() || "(no subject)";
        const body = reader.querySelector(".body").value.trim();
        if (!body) return;
        const btn = reader.querySelector(".send"); btn.disabled = true; btn.textContent = "Sending…";
        const t = await (await fetch(`/api/session/${sid}/mail/compose`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ to, subject, body }) })).json();
        activeId = t.id; renderThread(t); loadThreads();
      };
    }

    function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

    q(".compose-btn").onclick = compose;
    loadThreads();
    return { unmount() {} };
  }
});
