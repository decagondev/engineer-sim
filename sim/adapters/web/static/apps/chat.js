SimApps.register({
  id: "chat",
  title: "Team Chat",
  accent: "#3b6ef5",
  icon: '<svg viewBox="0 0 24 24"><path d="M4 5h16a1.5 1.5 0 0 1 1.5 1.5v9A1.5 1.5 0 0 1 20 17H9l-4 3v-3h-1a1.5 1.5 0 0 1-1.5-1.5v-9A1.5 1.5 0 0 1 4 5z" stroke-linejoin="round"/></svg>',
  css: `
  .chat-app{display:flex;height:100%}
  .chat-app .roster{width:250px;flex:none;background:var(--panel);border-right:1px solid var(--line);display:flex;flex-direction:column}
  .chat-app .who-label{padding:14px 16px 6px;font-size:12px;color:var(--muted)}
  .chat-app .people{flex:1;overflow-y:auto;padding:0 8px}
  .chat-app .person{display:flex;gap:10px;align-items:center;padding:9px 8px;border-radius:9px;cursor:pointer;position:relative}
  .chat-app .person:hover,.chat-app .person.active{background:var(--panel-2)}
  .chat-app .person.active::before{content:"";position:absolute;left:0;top:8px;bottom:8px;width:3px;border-radius:2px;background:var(--me)}
  .chat-app .avatar{width:34px;height:34px;flex:none;border-radius:9px;display:grid;place-items:center;font-size:13px;font-weight:600;color:#0d0f13}
  .chat-app .person .meta{min-width:0;flex:1}
  .chat-app .person .name{font-size:14px;font-weight:550;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .chat-app .person .role{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .chat-app .unread{margin-left:auto;min-width:18px;height:18px;padding:0 5px;border-radius:9px;background:var(--me);color:#fff;font-size:11px;font-weight:600;display:grid;place-items:center}
  .chat-app .person.enter{animation:cx-enter .45s cubic-bezier(.2,.8,.2,1)}
  @keyframes cx-enter{from{opacity:0;transform:translateX(-8px)}to{opacity:1;transform:none}}
  .chat-app .cmain{flex:1;display:flex;flex-direction:column;min-width:0}
  .chat-app .ctop{padding:11px 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px}
  .chat-app .ctop .peer{display:flex;gap:10px;align-items:center;min-width:0}
  .chat-app .ctop .peer .name{font-weight:600}
  .chat-app .ctop .peer .role{color:var(--muted);font-size:13px}
  .chat-app .ctop .gradeBtn{margin-left:auto;background:var(--panel-2);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:7px 12px;font-size:13px;cursor:pointer}
  .chat-app .ctop .gradeBtn:hover{border-color:#3a4353}
  .chat-app .ctop .gopts{margin-left:auto;display:flex;align-items:center;gap:10px}
  .chat-app .ctop .gopts label{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);cursor:pointer;user-select:none}
  .chat-app .grade{padding:0 16px 6px;white-space:pre-wrap;font:12.5px/1.6 var(--mono);color:var(--muted)}
  .chat-app .diagram{margin:0 16px 8px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--panel);font:12.5px/1.5 var(--mono);color:var(--muted);white-space:pre-wrap;display:none}
  .chat-app .log{flex:1;overflow-y:auto;padding:18px 16px;display:flex;flex-direction:column;gap:2px}
  .chat-app .row{display:flex;flex-direction:column;max-width:74%}
  .chat-app .row:has(.md-code){max-width:88%}
  .chat-app .row.me{align-self:flex-end;align-items:flex-end}
  .chat-app .row.them{align-self:flex-start;align-items:flex-start}
  .chat-app .metline{font-size:11px;color:var(--muted);margin:8px 6px 3px;display:flex;gap:8px;align-items:baseline}
  .chat-app .metline .t{font-family:var(--mono);color:var(--faint)}
  .chat-app .bubble{padding:9px 13px;border-radius:15px;word-wrap:break-word;overflow-wrap:anywhere}
  .chat-app .me .bubble{background:var(--me);color:var(--me-ink);border-bottom-right-radius:5px}
  .chat-app .them .bubble{background:var(--them);border:1px solid var(--line);border-bottom-left-radius:5px}
  .chat-app .me .bubble.md a{color:#fff}
  .chat-app .me .bubble.md li::marker{color:rgba(255,255,255,.72)}
  .chat-app .me .bubble.md blockquote{border-color:rgba(255,255,255,.35);color:rgba(255,255,255,.88)}
  .chat-app .me .bubble.md hr{border-color:rgba(255,255,255,.25)}
  .chat-app .me .bubble.md code{background:rgba(0,0,0,.22);border-color:rgba(255,255,255,.18)}
  .chat-app .me .bubble.md th{background:rgba(255,255,255,.12)}
  .chat-app .signal{align-self:center;max-width:82%;text-align:center;margin:10px 0;font:12px/1.5 var(--mono);color:var(--sig);background:var(--sig-bg);border:1px solid var(--sig-line);border-radius:8px;padding:5px 12px}
  .chat-app .empty{margin:auto;color:var(--muted);text-align:center;font-size:14px}
  .chat-app .typing{align-self:flex-start;display:flex;gap:4px;padding:11px 14px;background:var(--them);border:1px solid var(--line);border-radius:15px;border-bottom-left-radius:5px;margin-top:8px}
  .chat-app .typing span{width:6px;height:6px;border-radius:50%;background:var(--muted);animation:cx-blink 1.2s infinite}
  .chat-app .typing span:nth-child(2){animation-delay:.2s}
  .chat-app .typing span:nth-child(3){animation-delay:.4s}
  @keyframes cx-blink{0%,60%,100%{opacity:.25}30%{opacity:1}}
  .chat-app .composer{display:flex;gap:10px;padding:13px 14px;border-top:1px solid var(--line)}
  .chat-app .composer input{flex:1;background:var(--panel);border:1px solid var(--line);color:var(--text);border-radius:11px;padding:11px 14px;font:inherit;outline:none}
  .chat-app .composer input:focus{border-color:var(--me)}
  .chat-app .composer .send{background:var(--me);border:1px solid var(--me);color:#fff;font-weight:600;border-radius:11px;padding:0 16px;cursor:pointer}
  @media (max-width:720px){.chat-app .roster{width:190px}.chat-app .row{max-width:88%}}
  `,
  mount(root, ctx) {
    root.innerHTML = `<div class="chat-app">
      <aside class="roster">
        <div class="who-label">People</div>
        <div class="people"></div>
      </aside>
      <section class="cmain">
        <div class="ctop"><div class="peer"></div>
          <div class="gopts">
            <label class="ticketsToggle" hidden><input type="checkbox" class="includeTickets"/> Include tickets extra credit</label>
            <button class="gradeBtn" type="button">Grade run</button>
          </div>
        </div>
        <div class="grade"></div>
        <div class="diagram"></div>
        <div class="log"></div>
        <form class="composer" autocomplete="off">
          <input class="input" placeholder="Type a message…" autofocus/>
          <button class="send" type="submit">Send</button>
        </form>
      </section>
    </div>`;
    const app = root.querySelector(".chat-app"), q = s => app.querySelector(s);
    const log = q(".log"), input = q(".input"), sendBtn = q(".send"),
          peopleEl = q(".people"), peerEl = q(".peer"), gradeOut = q(".grade"),
          diagramEl = q(".diagram");
    if (window.SimMD) SimMD.hydrate(log);
    const sid = ctx.sid;
    const interview = ctx.scenario && ctx.scenario.track === "interview";
    if (interview) q(".ticketsToggle").hidden = false;
    let meta = {}, primaryKey = null, active = null, awaiting = null, watchdog = null, ws = null, closed = false, seen = new Set(), pollTimer = null;
    const channels = {};
    const HUES = [210, 28, 150, 280, 340, 95];
    const hueFor = k => { let h = 0; for (const c of k) h = (h * 31 + c.charCodeAt(0)) >>> 0; return HUES[h % HUES.length]; };
    const initials = n => n.split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
    const fmt = ts => { const d = new Date(ts); return isNaN(d) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); };

    function renderRoster() {
      peopleEl.innerHTML = "";
      Object.keys(channels).forEach(key => {
        const m = meta[key] || { name: key, role: "" }, h = hueFor(key);
        const row = document.createElement("div");
        row.className = "person" + (key === active ? " active" : ""); row.tabIndex = 0;
        row.innerHTML = `<div class="avatar" style="background:hsl(${h} 55% 62%)">${initials(m.name)}</div>` +
          `<div class="meta"><div class="name">${m.name}</div><div class="role">${m.role || ""}</div></div>` +
          (channels[key].unread ? `<div class="unread">${channels[key].unread}</div>` : "");
        row.onclick = () => setActive(key);
        row.onkeydown = e => { if (e.key === "Enter" || e.key === " ") setActive(key); };
        peopleEl.appendChild(row);
      });
    }
    function renderPeer() {
      const m = meta[active] || { name: active, role: "" }, h = hueFor(active);
      peerEl.innerHTML = `<div class="avatar" style="width:26px;height:26px;border-radius:7px;background:hsl(${h} 55% 62%)">${initials(m.name)}</div>` +
        `<div><span class="name">${m.name}</span> <span class="role">${m.role || ""}</span></div>`;
    }
    function renderLog() {
      log.innerHTML = "";
      const ch = channels[active];
      if (!ch || ch.messages.length === 0) {
        const e = document.createElement("div"); e.className = "empty";
        e.textContent = `No messages yet. Say hello to ${(meta[active] || {}).name || "them"}.`;
        log.appendChild(e); return;
      }
      for (const msg of ch.messages) log.appendChild(renderMsg(msg));
      if (awaiting === active) log.appendChild(typingEl());
      log.scrollTop = log.scrollHeight;
    }
    function renderMsg(msg) {
      if (msg.kind === "signal") { const s = document.createElement("div"); s.className = "signal"; s.textContent = msg.content; return s; }
      const mine = msg.sender === "tester";
      const row = document.createElement("div"); row.className = "row " + (mine ? "me" : "them");
      const met = document.createElement("div"); met.className = "metline";
      const who = mine ? "You" : ((meta[msg.sender] || {}).name || msg.sender);
      met.innerHTML = `<span>${who}</span><span class="t">${fmt(msg.ts)}</span>`;
      const b = document.createElement("div"); b.className = "bubble md";
      if (window.SimMD) b.innerHTML = SimMD.render(msg.content);
      else b.textContent = msg.content;
      row.appendChild(met); row.appendChild(b); return row;
    }
    function typingEl() { const t = document.createElement("div"); t.className = "typing"; t.innerHTML = "<span></span><span></span><span></span>"; return t; }

    function ensureChannel(key, o = {}) {
      if (channels[key]) return false;
      channels[key] = { messages: [], unread: 0 }; renderRoster();
      if (!o.replay && key !== primaryKey) {
        signal(key, `${(meta[key] || {}).name || key} joined the conversation`);
        const node = [...peopleEl.children].find(n => n.querySelector(".name") && n.querySelector(".name").textContent === (meta[key] || {}).name);
        if (node) node.classList.add("enter");
      }
      return true;
    }
    function signal(key, text) { (channels[key] || (channels[key] = { messages: [], unread: 0 })).messages.push({ kind: "signal", content: text }); if (key === active) renderLog(); }
    function push(key, msg) { channels[key].messages.push(msg); if (key === active) renderLog(); else { channels[key].unread++; renderRoster(); } }
    function incoming(m, o = {}) {
      const keyId = m.id != null ? "id:" + m.id : "";
      const keyTxt = [m.sender, m.ts, m.kind || "message", (m.content || "").slice(0, 160)].join("|");
      if ((keyId && seen.has(keyId)) || seen.has(keyTxt)) return;
      if (keyId) seen.add(keyId);
      seen.add(keyTxt);
      if (m.kind === "event" && m.content.startsWith("[fired:")) return;
      if (m.channel === "general") { if (primaryKey) signal(primaryKey, m.content.replace(/\.$/, "")); return; }
      const key = m.channel.startsWith("dm:") ? m.channel.slice(3) : m.channel;
      if (m.kind === "event") { ensureChannel(key, o); signal(key, m.content.replace(/^\[reveal\]\s*/, "")); return; }
      ensureChannel(key, o); push(key, m);
      if (!o.replay && m.sender === awaiting) clearAwaiting();
    }
    function setActive(key) { active = key; if (channels[key]) channels[key].unread = 0; renderRoster(); renderPeer(); renderLog(); input.focus(); }
    function clearAwaiting() { awaiting = null; clearTimeout(watchdog); sendBtn.disabled = false; input.disabled = false; input.focus(); if (active) renderLog(); }

    function connect() {
      ws = new WebSocket(`ws://${location.host}/ws/${sid}`);
      ws.onmessage = e => {
        const m = JSON.parse(e.data);
        if (m.error || m.kind === "error") {
          const key = active || primaryKey;
          if (key) signal(key, m.error || "the model failed to reply");
          clearAwaiting();
          return;
        }
        incoming(m);
      };
      ws.onclose = () => { if (!closed && primaryKey) signal(primaryKey, "disconnected — reopen Team Chat to reconnect"); sendBtn.disabled = true; };
    }

    (async function boot() {
      const sc = ctx.scenario;
      sc.personas.forEach(p => meta[p.key] = { name: p.name, role: p.role });
      primaryKey = sc.personas[0].key;
      const history = await (await fetch(`/api/session/${sid}/transcript`)).json();
      ensureChannel(primaryKey, { replay: true });
      if (history.length === 0) {
        await fetch(`/api/session/${sid}/start`, { method: "POST" });
        (await (await fetch(`/api/session/${sid}/transcript`)).json()).forEach(m => incoming(m, { replay: true }));
      } else {
        history.forEach(m => incoming(m, { replay: true }));
      }
      setActive(primaryKey); connect();
    })();

    q(".composer").addEventListener("submit", e => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text || !ws || ws.readyState !== 1) return;
      push(active, { sender: "tester", content: text, channel: "dm:" + active, ts: new Date().toISOString(), kind: "message" });
      ws.send(JSON.stringify({ content: text, target: active }));
      input.value = ""; awaiting = active; sendBtn.disabled = true; input.disabled = true; renderLog();
      clearTimeout(watchdog);
      watchdog = setTimeout(() => { if (awaiting) { signal(active, "no response yet — you can keep typing"); clearAwaiting(); } }, 120000);
    });

    async function refreshDiagram() {
      try {
        const d = await (await fetch(`/api/session/${sid}/diagram`)).json();
        if (!d.mermaid) return;
        diagramEl.style.display = "block";
        const src = "```mermaid\n" + d.mermaid + "\n```";
        if (window.SimMD) diagramEl.innerHTML = "<div class='muted' style='margin-bottom:6px'>Design diagram</div>" + SimMD.render(src);
        else diagramEl.textContent = d.mermaid;
      } catch (e) {}
    }

    q(".gradeBtn").addEventListener("click", async () => {
      gradeOut.textContent = "Grading this run…";
      const includeTickets = interview && q(".includeTickets").checked;
      const g = await (await fetch(`/api/session/${sid}/grade`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ include_tickets: includeTickets })
      })).json();
      if (g.error) { gradeOut.textContent = "grade error: " + g.error; return; }
      const rows = g.scores.map(s => `  ${s.key.padEnd(14)} ${String((s.score * 100 | 0) + "%").padStart(4)}   ${s.evidence}`).join("\n");
      const extra = g.tickets_extra
        ? `\n  ${"tickets+".padEnd(14)} ${String((g.tickets_extra.score * 100 | 0) + "%").padStart(4)}   ${g.tickets_extra.evidence}`
        : "";
      const base = g.include_tickets ? `  (base ${(g.total_base * 100 | 0)}% + tickets extra credit)\n` : "";
      const caveat = g.calibrated ? "" : `\n\n! ${g.caveat || "grader not calibrated"}`;
      gradeOut.textContent = `SCORE ${(g.total * 100 | 0)}%\n${base}${rows}${extra}\n\n${g.summary}${caveat}`;
      refreshDiagram();
    });

    async function pollTranscript() {
      if (closed) return;
      try {
        const history = await (await fetch(`/api/session/${sid}/transcript`)).json();
        (history || []).forEach(m => incoming(m, { replay: true }));
        if (interview) refreshDiagram();
      } catch (e) {}
    }

    pollTimer = setInterval(pollTranscript, 4000);
    if (interview) refreshDiagram();

    return { unmount() { closed = true; if (ws) { ws.onclose = null; ws.close(); } clearTimeout(watchdog); clearInterval(pollTimer); } };
  }
});
