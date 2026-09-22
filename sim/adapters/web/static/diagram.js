/* SimDiagram: render mermaid fences as real diagrams wherever markdown is shown
   (Team Chat, the instructor replay, the Files preview). Uses the vendored
   mermaid build (static/vendor/mermaid, no CDN); without it, fences stay as
   highlighted code blocks, which is what SimMD already produces.

     SimDiagram.render(el, src)   // draw one diagram into el (falls back to a code block)
     SimDiagram.hydrate(root)     // draw every ```mermaid fence under root, now and as they arrive
*/
window.SimDiagram = (function () {
  let ready = false, seq = 0, loading = null;
  // 3 MB, so it is fetched the first time a diagram is actually drawn, not on
  // every page load. Pages no longer ship a <script> tag for it.
  const SRC = "/static/vendor/mermaid/mermaid.min.js";
  function ensure() {
    if (window.mermaid) return Promise.resolve(true);
    if (loading) return loading;
    loading = new Promise(resolve => {
      const s = document.createElement("script");
      s.src = SRC; s.async = true;
      s.onload = () => resolve(!!window.mermaid);
      s.onerror = () => { loading = null; resolve(false); };
      document.head.appendChild(s);
    });
    return loading;
  }
  const CSS = `
  .sim-diagram{margin:6px 0;padding:10px 12px;border:1px solid var(--line,#272e3a);border-radius:10px;background:var(--ink,#12151b);overflow-x:auto}
  .sim-diagram svg{max-width:100%;height:auto;display:block}
  .sim-diagram .cap{font:11px/1 var(--mono,monospace);color:var(--faint,#5c6575);letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px}
  .sim-diagram.err{border-color:rgba(224,101,92,.5)}
  .sim-diagram.err .why{font:12px var(--ui,sans-serif);color:#e5807a;margin-top:6px}
  `;
  function css() {
    if (document.getElementById("sim-diagram-css")) return;
    const s = document.createElement("style"); s.id = "sim-diagram-css"; s.textContent = CSS;
    document.head.appendChild(s);
  }
  function init() {
    if (ready || !window.mermaid) return !!ready;
    try {
      window.mermaid.initialize({
        startOnLoad: false, securityLevel: "strict", theme: "dark",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        themeVariables: { primaryColor: "#1f2632", primaryTextColor: "#e7eaf0", primaryBorderColor: "#3b6ef5",
                          lineColor: "#8a93a4", secondaryColor: "#161b23", tertiaryColor: "#1b212b",
                          background: "#12151b", mainBkg: "#1f2632", nodeBorder: "#3b6ef5", clusterBkg: "#161b23",
                          clusterBorder: "#272e3a", titleColor: "#e7eaf0", edgeLabelBackground: "#161b23" },
      });
      ready = true;
    } catch (e) { ready = false; }
    return ready;
  }

  // same surgery as sim/core/session/interview.py::repair_mermaid
  function repair(src) {
    const special = /[()\\/{}<>|:#;,&"']/;
    return String(src).split("\n").map(line => {
      const t = line.trim();
      if (/^(subgraph|%%|classDef|class |style |linkStyle)/.test(t)) return line;
      return line.replace(/\b([A-Za-z_][\w-]*)\[(?!")([^\]"]*?)\]/g, (m, name, label) => {
        const text = label.replace(/\\n/g, "<br/>").replace(/"/g, "'");
        return (special.test(label) || label.includes("\\n")) ? `${name}["${text}"]` : m;
      });
    }).join("\n");
  }

  async function render(el, src, caption, _retried) {
    css();
    const text = String(src || "").trim();
    if (!text) return false;
    if (!(await ensure()) || !init()) {
      // no mermaid: leave a highlighted code block so nothing is lost
      el.innerHTML = window.SimMD ? SimMD.render("```mermaid\n" + text + "\n```") : "<pre></pre>";
      if (!window.SimMD) el.querySelector("pre").textContent = text;
      return false;
    }
    const id = "simdg-" + (++seq) + "-" + Date.now().toString(36);
    try {
      const out = await window.mermaid.render(id, text);
      el.className = (el.className.replace(/\bsim-diagram\b|\berr\b/g, "") + " sim-diagram").trim();
      el.innerHTML = (caption ? `<div class="cap">${caption}</div>` : "") + out.svg;
      if (typeof out.bindFunctions === "function") out.bindFunctions(el);
      return true;
    } catch (e) {
      // mermaid leaves a stray element behind on a parse error
      const junk = document.getElementById("d" + id) || document.getElementById(id);
      if (junk && junk.parentNode) junk.parentNode.removeChild(junk);
      if (!_retried) {
        const fixed = repair(text);
        if (fixed !== text) return render(el, fixed, caption, true);
      }
      el.className = (el.className.replace(/\berr\b/g, "") + " sim-diagram err").trim();
      el.innerHTML = (caption ? `<div class="cap">${caption}</div>` : "") +
        (window.SimMD ? SimMD.render("```mermaid\n" + text + "\n```") : "") +
        `<div class="why">Could not draw this diagram: ${String(e && e.message || e).split("\n")[0]}</div>`;
      return false;
    }
  }

  // Replace ```mermaid fences (rendered by SimMD as .md-code[data-lang=mermaid])
  // with drawings. A MutationObserver catches blocks added later (chat replies,
  // replay steps, preview re-renders).
  function drawFences(root) {
    root.querySelectorAll('.md-code[data-lang="mermaid"]:not([data-drawn])').forEach(block => {
      block.setAttribute("data-drawn", "1");
      const code = block.querySelector("code");
      const src = code ? code.textContent : "";
      const holder = document.createElement("div");
      block.replaceWith(holder);
      render(holder, src, "diagram").then(ok => { if (!ok && !window.mermaid) holder.replaceWith(block); });
    });
  }
  function hydrate(root) {
    if (!root || root.__simDiagram) return;
    root.__simDiagram = true;
    css();
    drawFences(root);
    if ("MutationObserver" in window) {
      const mo = new MutationObserver(() => drawFences(root));
      mo.observe(root, { childList: true, subtree: true });
    }
  }
  return { render, hydrate, ensure, available: () => !!window.mermaid };
})();
