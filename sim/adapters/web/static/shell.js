/* Desktop shell + app registry.
   Adding an app is one register() call in its own file — the shell never changes.
   Apps mount into a floating window and share ctx (session id + scenario). */
window.SimApps = (function () {
  const apps = [];
  let current = null, handle = null;

  let sid = location.hash.slice(1);
  const ctx = { sid, scenario: null };
  const HOME = { admin: "/admin", instructor: "/instructor", challenger: "/challenger" };

  const $ = id => document.getElementById(id);

  function register(app) {
    apps.push(app);
    if (app.css && !document.getElementById("css-" + app.id)) {
      const s = document.createElement("style");
      s.id = "css-" + app.id; s.textContent = app.css;
      document.head.appendChild(s);
    }
  }

  function blocked(title, msg) {
    $("brand").textContent = title; $("hero").textContent = title; document.title = title;
    const sub = document.querySelector("#desktop .sub");
    if (sub) sub.textContent = msg;
    $("dock").innerHTML = "";
  }

  async function boot() {
    let gated = false, me = null;
    try {
      const cfg = await (await fetch("/api/auth/config")).json();
      gated = !!(cfg.auth_mode && cfg.auth_mode !== "password");
    } catch (e) {}
    if (gated) {
      if (!window.SimAuth || !SimAuth.token()) {
        location.href = "/login?next=/" + location.hash;
        return;
      }
      me = await SimAuth.me();
      if (!me) { SimAuth.signOut("/login?next=/" + location.hash); return; }
      if (!sid) {
        // Hosted sessions are created by an instructor; never mint one here.
        location.href = HOME[me.role] || "/challenger";
        return;
      }
    } else if (!sid) {
      sid = "s-" + Math.random().toString(36).slice(2, 9); location.hash = sid; ctx.sid = sid;
    }
    async function loadScenario() {
      const r = await fetch(`/api/session/${sid}/scenario`);
      return { ok: r.ok, status: r.status, body: await r.json().catch(() => ({})) };
    }
    let res;
    try {
      res = await loadScenario();
      if (res.status === 403 && me && me.role === "challenger") {
        // An unassigned session link: claim it, then try again.
        const c = await fetch(`/api/session/${sid}/claim`, { method: "POST" });
        if (c.ok) res = await loadScenario();
      }
    } catch (e) { res = { ok: false, status: 0, body: {} }; }
    if (!res.ok) {
      const why = res.status === 403
        ? "This session is not assigned to you. Open one from your dashboard, or ask your instructor for a link."
        : res.status === 401
          ? "Your sign-in has expired. Please sign in again."
          : "Could not load this session. Check your connection and refresh.";
      blocked("No access", why);
      if (res.status === 401 && window.SimAuth) SimAuth.signOut("/login?next=/" + location.hash);
      return;
    }
    ctx.scenario = res.body;
    if (!Array.isArray(ctx.scenario.personas)) ctx.scenario.personas = [];
    const title = ctx.scenario.title || "Workstation";
    $("brand").textContent = title;
    $("hero").textContent = title;
    document.title = title;
    if (ctx.scenario.track === "systems") {
      const sub = document.querySelector("#desktop .sub");
      if (sub) sub.textContent = "You are the Systems Designer. Discover constraints in Team Chat, write the design in the starter, then submit and defend it.";
    } else if (ctx.scenario.track === "interview") {
      const sub = document.querySelector("#desktop .sub");
      if (sub) sub.textContent = "Interview assessment. Ask the interviewer clarifying questions, write DESIGN.md, submit it, then defend your decisions with the assessor.";
    }
    renderDock();
    tick(); setInterval(tick, 1000);
    pollMail(); setInterval(pollMail, 6000);
    $("close").onclick = close;
  }

  function renderDock() {
    const dock = $("dock"); dock.innerHTML = "";
    apps.forEach(app => {
      const it = document.createElement("div");
      it.className = "dockitem" + (app.status ? " stub" : "") + (current && current.id === app.id ? " active" : "");
      it.tabIndex = 0; it.dataset.app = app.id;
      it.innerHTML = app.icon + `<span class="tip">${app.title}${app.status ? " — " + app.status : ""}</span>` +
        `<span class="badge" data-badge="${app.id}"></span>`;
      it.onclick = () => open(app.id);
      it.onkeydown = e => { if (e.key === "Enter" || e.key === " ") open(app.id); };
      dock.appendChild(it);
    });
  }

  function open(id) {
    const app = apps.find(a => a.id === id);
    if (!app) return;
    if (current && current.id === id) return;   // already open
    if (current) close();
    $("wintitle").textContent = app.title;
    $("appname").textContent = app.title;
    $("winbody").innerHTML = "";
    $("desktop").style.display = "none";
    $("window").style.display = "flex";
    handle = app.mount($("winbody"), ctx) || null;
    current = app;
    renderDock();
  }

  function close() {
    if (handle && typeof handle.unmount === "function") { try { handle.unmount(); } catch (e) {} }
    handle = null; current = null;
    $("winbody").innerHTML = "";
    $("window").style.display = "none";
    $("desktop").style.display = "flex";
    $("appname").textContent = "";
    renderDock();
  }

  async function pollMail() {
    try {
      const r = await (await fetch(`/api/session/${sid}/mail/unread`)).json();
      const b = document.querySelector('[data-badge="email"]');
      if (b) { if (r.count > 0) { b.textContent = r.count; b.classList.add('on'); } else b.classList.remove('on'); }
    } catch (e) {}
  }

  function tick() {
    $("clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  return { register, boot, open, close };
})();
