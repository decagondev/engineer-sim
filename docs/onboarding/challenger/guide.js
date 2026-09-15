/* Onboarding guides: shared behaviour (identical copy in each role folder).
   - step checklist persisted per guide in localStorage
   - rail progress + current-section highlight
   - copy buttons on commands
   - light/dark toggle (falls back to the system theme)                      */
(function () {
  const guide = document.body.dataset.guide || "guide";
  const KEY = "sim-onboarding:" + guide;
  const steps = [...document.querySelectorAll(".step[id]")];
  const rail = document.querySelector(".rail");

  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } }
  function save(state) { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  let state = load();

  // ---- rail --------------------------------------------------------------
  if (rail && steps.length) {
    const list = rail.querySelector("ol");
    steps.forEach((s, i) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = "#" + s.id;
      a.innerHTML = `<span class="n">${String(i + 1).padStart(2, "0")}</span><span>${s.dataset.short || s.querySelector("h2").textContent}</span>`;
      li.appendChild(a); list.appendChild(li);
    });
    const reset = rail.querySelector(".reset");
    if (reset) reset.onclick = () => { state = {}; save(state); render(); };
  }

  // ---- checkboxes ---------------------------------------------------------
  steps.forEach(s => {
    const box = s.querySelector(".check input");
    if (!box) return;
    box.checked = !!state[s.id];
    box.addEventListener("change", () => { state[s.id] = box.checked; save(state); render(); });
  });

  function render() {
    let done = 0;
    steps.forEach((s, i) => {
      const on = !!state[s.id];
      s.classList.toggle("done", on);
      const box = s.querySelector(".check input"); if (box) box.checked = on;
      const a = rail && rail.querySelectorAll("li a")[i]; if (a) a.classList.toggle("done", on);
      if (on) done++;
    });
    const p = rail && rail.querySelector(".prog span"); if (p) p.textContent = `${done} / ${steps.length}`;
    const bar = rail && rail.querySelector(".bar i"); if (bar) bar.style.width = (steps.length ? (done / steps.length) * 100 : 0) + "%";
  }
  render();

  // ---- current section ------------------------------------------------------
  if (rail && "IntersectionObserver" in window) {
    const links = [...rail.querySelectorAll("li a")];
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        const i = steps.indexOf(e.target);
        links.forEach((l, j) => l.classList.toggle("on", i === j));
      });
    }, { rootMargin: "-20% 0px -70% 0px", threshold: 0 });
    steps.forEach(s => io.observe(s));
  }

  // ---- copy buttons -----------------------------------------------------------
  document.querySelectorAll(".cmd").forEach(box => {
    const b = document.createElement("button"); b.type = "button"; b.textContent = "Copy";
    b.onclick = async () => {
      const text = box.dataset.copy || box.textContent.replace(/\s*Copy$/, "");
      try { await navigator.clipboard.writeText(text.trim()); b.textContent = "Copied"; }
      catch (e) { b.textContent = "Select & copy"; }
      setTimeout(() => { b.textContent = "Copy"; }, 1600);
    };
    box.appendChild(b);
  });

  // ---- theme toggle -------------------------------------------------------
  const t = document.querySelector(".theme");
  if (t) {
    const TK = "sim-onboarding:theme";
    const apply = v => { if (v) document.documentElement.dataset.theme = v; else delete document.documentElement.dataset.theme;
      t.textContent = v === "dark" ? "Light theme" : v === "light" ? "System theme" : "Dark theme"; };
    let cur = ""; try { cur = localStorage.getItem(TK) || ""; } catch (e) {}
    apply(cur);
    t.onclick = () => { cur = cur === "" ? "dark" : cur === "dark" ? "light" : ""; try { localStorage.setItem(TK, cur); } catch (e) {} apply(cur); };
  }

  // ---- fill the deployment host into links when served by the app --------------
  if (location.protocol.startsWith("http")) {
    document.querySelectorAll("[data-host-link]").forEach(a => { a.href = location.origin + a.dataset.hostLink; });
  }
})();
