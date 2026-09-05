/* Desktop shell + app registry.
   Adding an app is one register() call in its own file — the shell never changes.
   Apps mount into a floating window and share ctx (session id + scenario). */
window.SimApps = (function () {
  const apps = [];
  let current = null, handle = null;

  let sid = location.hash.slice(1);
  if (!sid) { sid = "s-" + Math.random().toString(36).slice(2, 9); location.hash = sid; }
  const ctx = { sid, scenario: null };

  const $ = id => document.getElementById(id);

  function register(app) {
    apps.push(app);
    if (app.css && !document.getElementById("css-" + app.id)) {
      const s = document.createElement("style");
      s.id = "css-" + app.id; s.textContent = app.css;
      document.head.appendChild(s);
    }
  }

  async function boot() {
    try { ctx.scenario = await (await fetch(`/api/session/${sid}/scenario`)).json(); }
    catch (e) { ctx.scenario = { title: "Workstation", personas: [] }; }
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
