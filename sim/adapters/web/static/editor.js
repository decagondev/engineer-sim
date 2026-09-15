/* SimEditor: one code editor for every app. Backed by the vendored CodeMirror 5
   (static/vendor/codemirror, no CDN so it works on a classroom LAN); falls back
   to a plain <textarea> with the same API when the vendor files are missing.

     const ed = SimEditor.mount(el, { path, text, readOnly, onSave, onChange });
     ed.getValue(); ed.setValue(text); ed.focus(); ed.setReadOnly(bool); ed.destroy();
*/
window.SimEditor = (function () {
  const MODES = {
    md: "markdown", markdown: "markdown", py: "python", js: "javascript", mjs: "javascript",
    ts: "javascript", json: { name: "javascript", json: true }, yaml: "yaml", yml: "yaml",
    css: "css", html: "htmlmixed", htm: "htmlmixed", xml: "xml", svg: "xml",
    sql: "sql", sh: "shell", bash: "shell", txt: null,
  };

  const CSS = `
  .sim-ed{position:absolute;inset:0;display:flex;flex-direction:column}
  .sim-ed .CodeMirror{flex:1;height:auto;min-height:0;font:12.5px/1.6 var(--mono);
    background:var(--ink);color:var(--text)}
  .sim-ed .CodeMirror-gutters{background:var(--ink);border-right:1px solid var(--line)}
  .sim-ed .CodeMirror-linenumber{color:var(--faint)}
  .sim-ed .CodeMirror-cursor{border-left:1.5px solid var(--text)}
  .sim-ed .CodeMirror-activeline-background{background:rgba(255,255,255,.035)}
  .sim-ed .CodeMirror-selected{background:rgba(59,110,245,.28)}
  .sim-ed .CodeMirror-focused .CodeMirror-selected{background:rgba(59,110,245,.38)}
  .sim-ed .CodeMirror-matchingbracket{color:#fff!important;background:rgba(202,162,74,.35)}
  .sim-ed .cm-s-sim .cm-keyword{color:#c792ea}
  .sim-ed .cm-s-sim .cm-def,.sim-ed .cm-s-sim .cm-variable-2{color:#82aaff}
  .sim-ed .cm-s-sim .cm-string,.sim-ed .cm-s-sim .cm-string-2{color:#c3e88d}
  .sim-ed .cm-s-sim .cm-number,.sim-ed .cm-s-sim .cm-atom{color:#f78c6c}
  .sim-ed .cm-s-sim .cm-comment{color:#66707d;font-style:italic}
  .sim-ed .cm-s-sim .cm-builtin,.sim-ed .cm-s-sim .cm-type{color:#ffcb6b}
  .sim-ed .cm-s-sim .cm-property,.sim-ed .cm-s-sim .cm-attribute{color:#ffcb6b}
  .sim-ed .cm-s-sim .cm-tag,.sim-ed .cm-s-sim .cm-error{color:#f07178}
  .sim-ed .cm-s-sim .cm-meta,.sim-ed .cm-s-sim .cm-qualifier{color:#89ddff}
  .sim-ed .cm-s-sim .cm-header{color:#82aaff;font-weight:600}
  .sim-ed .cm-s-sim .cm-quote{color:#8a93a4;font-style:italic}
  .sim-ed .cm-s-sim .cm-link{color:#89ddff;text-decoration:underline}
  .sim-ed .cm-s-sim .cm-strong{font-weight:700}.sim-ed .cm-s-sim .cm-em{font-style:italic}
  .sim-ed .cm-s-sim .cm-hr{color:var(--faint)}
  .sim-ed .CodeMirror-dialog{background:var(--panel);color:var(--text);border-bottom:1px solid var(--line);font:13px var(--ui)}
  .sim-ed .CodeMirror-dialog input{background:var(--ink);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:2px 6px;font:inherit}
  .sim-ed .CodeMirror-search-hint{color:var(--muted)}
  .sim-ed textarea.fallback{flex:1;width:100%;resize:none;border:0;outline:0;margin:0;padding:14px 16px;
    background:var(--ink);color:var(--text);font:12.5px/1.6 var(--mono);tab-size:2;white-space:pre}
  `;

  function ensureCss() {
    if (document.getElementById("sim-editor-css")) return;
    const s = document.createElement("style"); s.id = "sim-editor-css"; s.textContent = CSS;
    document.head.appendChild(s);
  }

  function modeFor(path) {
    const ext = (path || "").split(".").pop().toLowerCase();
    return Object.prototype.hasOwnProperty.call(MODES, ext) ? MODES[ext] : null;
  }

  function mount(el, opts) {
    opts = opts || {};
    ensureCss();
    const host = document.createElement("div"); host.className = "sim-ed";
    el.appendChild(host);
    const CM = window.CodeMirror;
    let readOnly = !!opts.readOnly;

    if (!CM) {
      // vendor files missing: a plain textarea keeps the app usable
      const ta = document.createElement("textarea"); ta.className = "fallback";
      ta.value = opts.text || ""; ta.readOnly = readOnly; ta.spellcheck = false;
      ta.addEventListener("input", () => opts.onChange && opts.onChange());
      ta.addEventListener("keydown", e => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); opts.onSave && opts.onSave(); }
      });
      host.appendChild(ta);
      return {
        getValue: () => ta.value, setValue: v => { ta.value = v; },
        focus: () => ta.focus(), setReadOnly: v => { readOnly = !!v; ta.readOnly = readOnly; },
        setPath: () => {}, destroy: () => host.remove(), backend: "textarea",
      };
    }

    const cm = CM(host, {
      value: opts.text || "",
      mode: modeFor(opts.path),
      theme: "sim",
      lineNumbers: true,
      lineWrapping: modeFor(opts.path) === "markdown",
      styleActiveLine: true,
      matchBrackets: true,
      autoCloseBrackets: true,
      indentUnit: 2, tabSize: 2, indentWithTabs: false,
      readOnly: readOnly ? "nocursor" : false,
      viewportMargin: 50,
      extraKeys: {
        "Ctrl-S": () => opts.onSave && opts.onSave(),
        "Cmd-S": () => opts.onSave && opts.onSave(),
        "Tab": c => { if (c.somethingSelected()) c.indentSelection("add"); else c.replaceSelection("  ", "end"); },
        "Shift-Tab": c => c.indentSelection("subtract"),
      },
    });
    cm.on("change", () => opts.onChange && opts.onChange());
    setTimeout(() => cm.refresh(), 0);

    return {
      getValue: () => cm.getValue(),
      setValue: v => { cm.setValue(v || ""); cm.clearHistory(); },
      focus: () => cm.focus(),
      refresh: () => cm.refresh(),
      setReadOnly: v => { readOnly = !!v; cm.setOption("readOnly", readOnly ? "nocursor" : false); },
      setPath: p => { const m = modeFor(p); cm.setOption("mode", m); cm.setOption("lineWrapping", m === "markdown"); },
      destroy: () => { host.remove(); },
      backend: "codemirror",
    };
  }

  return { mount, modeFor };
})();
