/* Safe markdown + syntax highlighting for chat / replay. No CDN. */
(function (global) {
  function esc(s) {
    return String(s).replace(/[&<>"']/g, c => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function paint(src, rules) {
    let out = "", i = 0;
    while (i < src.length) {
      let hit = null;
      for (const [type, re] of rules) {
        re.lastIndex = i;
        const m = re.exec(src);
        if (m) { hit = [type, m[0]]; break; }
      }
      if (!hit) { out += esc(src[i]); i += 1; continue; }
      out += hit[0] ? `<span class="tok-${hit[0]}">${esc(hit[1])}</span>` : esc(hit[1]);
      i += hit[1].length;
    }
    return out;
  }

  const KW = {
    py: "False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield|match|case",
    js: "async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|finally|for|function|if|import|in|instanceof|let|new|of|return|static|super|switch|throw|try|typeof|var|void|while|with|yield",
    ts: "abstract|as|asserts|extends|implements|infer|interface|keyof|namespace|never|readonly|satisfies|type|unique",
    go: "break|case|chan|const|continue|default|defer|else|fallthrough|for|func|go|goto|if|import|interface|map|package|range|return|select|struct|switch|type|var",
    sql: "add|all|alter|and|as|asc|between|by|case|check|column|create|cross|delete|desc|distinct|drop|else|end|except|exists|from|full|group|having|in|inner|insert|intersect|into|is|join|left|like|limit|not|null|on|or|order|outer|primary|right|select|set|table|then|union|unique|update|values|when|where|with",
    sh: "alias|break|case|continue|do|done|elif|else|esac|export|fi|for|function|if|in|local|return|select|then|time|until|while",
  };

  function hlPython(s) {
    return paint(s, [
      ["cm", /#.*$/ym],
      ["str", /(?:[fFrRbBuU]{1,3})?(?:'''[\s\S]*?'''|"""[\s\S]*?"""|'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")/y],
      ["kw", new RegExp("\\b(?:" + KW.py + ")\\b", "y")],
      ["type", /\b(?:abs|all|any|bool|dict|enumerate|filter|float|int|len|list|map|open|print|range|set|str|sum|tuple|type|zip|self|cls)\b/y],
      ["meta", /@[\w.]+/y],
      ["fn", /[A-Za-z_]\w*(?=\s*\()/y],
      ["num", /\b(?:0[xX][\da-fA-F]+|0[bB][01]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b/y],
      [null, /\s+/y],
    ]);
  }

  function hlJs(s, extraKw) {
    const kw = extraKw ? KW.js + "|" + extraKw : KW.js;
    return paint(s, [
      ["cm", /\/\/.*$/ym],
      ["cm", /\/\*[\s\S]*?\*\//y],
      ["str", /`(?:\\.|\$\{(?:[^{}]|\{[^}]*\})*\}|[^\\`$])*`/y],
      ["str", /'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"/y],
      ["kw", new RegExp("\\b(?:" + kw + ")\\b", "y")],
      ["type", /\b(?:true|false|null|undefined|NaN|Infinity|this|super)\b/y],
      ["fn", /[A-Za-z_$][\w$]*(?=\s*\()/y],
      ["num", /\b(?:0[xX][\da-fA-F]+|0[bB][01]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b/y],
      [null, /\s+/y],
    ]);
  }

  function hlJson(s) {
    return paint(s, [
      ["key", /"(?:\\.|[^"\\])*"(?=\s*:)/y],
      ["str", /"(?:\\.|[^"\\])*"/y],
      ["type", /\b(?:true|false|null)\b/y],
      ["num", /-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/y],
      [null, /\s+/y],
    ]);
  }

  function hlYaml(s) {
    return paint(s, [
      ["cm", /#.*$/ym],
      ["key", /^[\t ]*[\w./-]+(?=\s*:)/ym],
      ["str", /'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"/y],
      ["type", /\b(?:true|false|null|yes|no|on|off)\b/iy],
      ["num", /-?\b\d+(?:\.\d+)?\b/y],
      [null, /\s+/y],
    ]);
  }

  function hlHtml(s) {
    return paint(s, [
      ["cm", /<!--[\s\S]*?-->/y],
      ["meta", /<!DOCTYPE[^>]+>/iy],
      ["tag", /<\/?[A-Za-z][\w:-]*/y],
      ["attr", /\s+[A-Za-z_:][\w:.-]*(?=\s*=)/y],
      ["str", /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/y],
      [null, /\s+/y],
    ]);
  }

  function hlCss(s) {
    return paint(s, [
      ["cm", /\/\*[\s\S]*?\*\//y],
      ["str", /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/y],
      ["kw", /@(?:import|media|keyframes|font-face|supports|charset)\b/y],
      ["type", /#[\w-]+/y],
      ["attr", /\.[\w-]+/y],
      ["fn", /[A-Za-z-]+(?=\s*\()/y],
      ["num", /#(?:[\da-fA-F]{3,8})\b|\b\d+(?:\.\d+)?(?:px|em|rem|%|vh|vw|s|ms)?\b/y],
      [null, /\s+/y],
    ]);
  }

  function hlBash(s) {
    return paint(s, [
      ["cm", /#.*$/ym],
      ["str", /'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"/y],
      ["kw", new RegExp("\\b(?:" + KW.sh + ")\\b", "y")],
      ["meta", /\$\{?[\w*@#?$!-]+\}?|\$\([^)]*\)/y],
      ["attr", /--?[\w-]+/y],
      [null, /\s+/y],
    ]);
  }

  function hlSql(s) {
    return paint(s, [
      ["cm", /--.*$/ym],
      ["cm", /\/\*[\s\S]*?\*\//y],
      ["str", /'(?:''|[^'])*'/y],
      ["kw", new RegExp("\\b(?:" + KW.sql + ")\\b", "iy")],
      ["num", /\b\d+(?:\.\d+)?\b/y],
      [null, /\s+/y],
    ]);
  }

  function hlDiff(s) {
    return paint(s, [
      ["meta", /^(?:diff |\+\+\+|---|index |@@).*$/ym],
      ["add", /^\+.*$/ym],
      ["del", /^-.*$/ym],
      [null, /^.*$/ym],
      [null, /\s+/y],
    ]);
  }

  function hlGo(s) {
    return paint(s, [
      ["cm", /\/\/.*$/ym],
      ["cm", /\/\*[\s\S]*?\*\//y],
      ["str", /`[^`]*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/y],
      ["kw", new RegExp("\\b(?:" + KW.go + ")\\b", "y")],
      ["type", /\b(?:bool|byte|complex64|complex128|error|float32|float64|int|int8|int16|int32|int64|rune|string|uint|uint8|uint16|uint32|uint64|uintptr|true|false|nil|iota)\b/y],
      ["fn", /[A-Za-z_]\w*(?=\s*\()/y],
      ["num", /\b\d+(?:\.\d+)?\b/y],
      [null, /\s+/y],
    ]);
  }

  const LANG = {
    python: hlPython, py: hlPython,
    javascript: s => hlJs(s), js: s => hlJs(s), jsx: s => hlJs(s), mjs: s => hlJs(s),
    typescript: s => hlJs(s, KW.ts), ts: s => hlJs(s, KW.ts), tsx: s => hlJs(s, KW.ts),
    json: hlJson, yaml: hlYaml, yml: hlYaml,
    html: hlHtml, xml: hlHtml, svg: hlHtml,
    css: hlCss, scss: hlCss,
    bash: hlBash, sh: hlBash, shell: hlBash, zsh: hlBash, powershell: hlBash, ps1: hlBash,
    sql: hlSql, diff: hlDiff, patch: hlDiff, go: hlGo, golang: hlGo,
  };

  const LANG_LABEL = {
    python: "Python", py: "Python", javascript: "JavaScript", js: "JavaScript",
    typescript: "TypeScript", ts: "TypeScript", json: "JSON", yaml: "YAML", yml: "YAML",
    html: "HTML", css: "CSS", bash: "Bash", sh: "Shell", sql: "SQL",
    diff: "Diff", patch: "Diff", go: "Go", rust: "Rust",
  };

  function highlight(code, lang) {
    const key = String(lang || "").trim().toLowerCase();
    const fn = LANG[key];
    return fn ? fn(code) : esc(code);
  }

  function inline(raw) {
    const stash = [];
    const hold = html => { stash.push(html); return `\x00H${stash.length - 1}\x00`; };
    let s = String(raw);
    s = s.replace(/`([^`\n]+)`/g, (_, c) => hold(`<code>${esc(c)}</code>`));
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/gi, (_, text, url) =>
      hold(`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`));
    s = esc(s);
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/__(.+?)__/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^\*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    s = s.replace(/(^|[\s(])_(?!_)([^_\s][^_\n]*?)_(?=[\s).,!?:;]|$)/g, "$1<em>$2</em>");
    s = s.replace(/~~(.+?)~~/g, "<del>$1</del>");
    s = s.replace(/\x00H(\d+)\x00/g, (_, i) => stash[+i]);
    return s;
  }

  function fenceHtml(lang, code) {
    const key = String(lang || "").trim().split(/\s+/)[0];
    const label = LANG_LABEL[key.toLowerCase()] || key || "code";
    return `<div class="md-code"><div class="md-code-bar"><span class="md-code-lang">${esc(label)}</span>` +
      `<button type="button" class="md-copy">Copy</button></div>` +
      `<pre><code>${highlight(code.replace(/\n$/, ""), key)}</code></pre></div>`;
  }

  function isList(line) { return /^\s*(?:[-*+]|\d+\.)\s+/.test(line); }
  function isTableRow(line) { return /^\s*\|.+\|\s*$/.test(line); }
  function isTableSep(line) { return /^\s*\|?\s*:?-{2,}.*\|\s*$/.test(line); }

  function renderTable(lines) {
    const cells = line => line.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
    const head = cells(lines[0]);
    const body = lines.slice(isTableSep(lines[1]) ? 2 : 1);
    let html = "<table><thead><tr>" + head.map(c => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
    for (const row of body) {
      html += "<tr>" + cells(row).map(c => `<td>${inline(c)}</td>`).join("") + "</tr>";
    }
    return html + "</tbody></table>";
  }

  function renderBlocks(text, fences) {
    const lines = text.split("\n");
    let html = "", i = 0;
    while (i < lines.length) {
      const line = lines[i];
      const ph = /^\x00F(\d+)\x00$/.exec(line);
      if (ph) { html += fences[+ph[1]]; i += 1; continue; }
      if (/^\s*$/.test(line)) { i += 1; continue; }
      if (/^\s*---+\s*$/.test(line)) { html += "<hr>"; i += 1; continue; }
      const h = /^(#{1,3})\s+(.+)$/.exec(line);
      if (h) { html += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; i += 1; continue; }
      if (/^\s*>/.test(line)) {
        const buf = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) {
          buf.push(lines[i].replace(/^\s*>\s?/, ""));
          i += 1;
        }
        html += `<blockquote>${renderBlocks(buf.join("\n"), fences)}</blockquote>`;
        continue;
      }
      if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        const buf = [];
        while (i < lines.length && (isTableRow(lines[i]) || isTableSep(lines[i]))) {
          buf.push(lines[i]); i += 1;
        }
        html += renderTable(buf);
        continue;
      }
      if (isList(line)) {
        const ordered = /^\s*\d+\./.test(line);
        const items = [];
        while (i < lines.length && isList(lines[i])) {
          items.push(lines[i].replace(/^\s*(?:[-*+]|\d+\.)\s+/, ""));
          i += 1;
          while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !isList(lines[i])) {
            items[items.length - 1] += " " + lines[i].trim();
            i += 1;
          }
        }
        const tag = ordered ? "ol" : "ul";
        html += `<${tag}>` + items.map(it => {
          const box = /^\[( |x|X)\]\s+/.exec(it);
          if (box) {
            const on = box[1] !== " ";
            return `<li class="md-check"><input type="checkbox" disabled${on ? " checked" : ""}> ${inline(it.slice(box[0].length))}</li>`;
          }
          return `<li>${inline(it)}</li>`;
        }).join("") + `</${tag}>`;
        continue;
      }
      const buf = [];
      while (i < lines.length && lines[i].trim() !== "" &&
             !/^\x00F\d+\x00$/.test(lines[i]) &&
             !/^#{1,3}\s+/.test(lines[i]) &&
             !isList(lines[i]) &&
             !/^\s*>/.test(lines[i]) &&
             !/^\s*---+\s*$/.test(lines[i])) {
        buf.push(lines[i]);
        i += 1;
      }
      if (buf.length) html += `<p>${buf.map(inline).join("<br>")}</p>`;
    }
    return html;
  }

  function render(src) {
    if (src == null || src === "") return "";
    let text = String(src).replace(/\r\n/g, "\n");
    const fences = [];
    text = text.replace(/^(```|~~~)([^\n]*)\n([\s\S]*?)^\1[ \t]*$/gm, (_, _t, lang, code) => {
      const id = fences.length;
      fences.push(fenceHtml(lang, code));
      return `\n\x00F${id}\x00\n`;
    });
    return renderBlocks(text, fences);
  }

  function hydrate(root) {
    if (!root) return;
    root.addEventListener("click", ev => {
      const btn = ev.target.closest(".md-copy");
      if (!btn || !root.contains(btn)) return;
      const code = btn.closest(".md-code") && btn.closest(".md-code").querySelector("code");
      if (!code) return;
      const done = () => { btn.textContent = "Copied"; setTimeout(() => { btn.textContent = "Copy"; }, 1200); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code.textContent).then(done).catch(() => {});
      }
    });
  }

  const CSS = `
  .md{line-height:1.55;overflow-wrap:anywhere;word-wrap:break-word}
  .md>:first-child{margin-top:0}
  .md>:last-child{margin-bottom:0}
  .md p{margin:0 0 .55em}
  .md p:last-child{margin-bottom:0}
  .md ul,.md ol{margin:.35em 0 .55em;padding-left:1.3em}
  .md li{margin:.18em 0}
  .md li.md-check{list-style:none;margin-left:-1.1em;display:flex;gap:7px;align-items:flex-start}
  .md li.md-check input{margin-top:.28em;accent-color:#3b6ef5}
  .md li::marker{color:var(--muted)}
  .md strong{font-weight:650}
  .md em{font-style:italic}
  .md h1,.md h2,.md h3{margin:.45em 0 .28em;font-weight:650;line-height:1.3}
  .md h1{font-size:1.12em}.md h2{font-size:1.05em}.md h3{font-size:1em}
  .md hr{border:none;border-top:1px solid var(--line);margin:.7em 0}
  .md blockquote{margin:.4em 0;padding:.1em 0 .1em .85em;border-left:3px solid var(--line);color:var(--muted)}
  .md a{color:#8eb4ff;text-decoration:underline;text-underline-offset:2px}
  .md table{border-collapse:collapse;margin:.5em 0;font-size:.95em;width:100%}
  .md th,.md td{border:1px solid var(--line);padding:4px 8px;text-align:left}
  .md th{background:rgba(255,255,255,.04);font-weight:600}
  .md code{font:12.5px/1.45 var(--mono);background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.08);border-radius:5px;padding:.08em .36em}
  .md-code{margin:.65em 0;border-radius:10px;overflow:hidden;background:#0b0e14;border:1px solid #2a3140}
  .md-code:first-child{margin-top:.15em}
  .md-code:last-child{margin-bottom:.1em}
  .md-code-bar{display:flex;align-items:center;gap:8px;padding:6px 10px;background:#12171f;border-bottom:1px solid #2a3140;font:11px/1 var(--mono);color:#8a93a4}
  .md-code-lang{letter-spacing:.02em}
  .md-copy{margin-left:auto;background:transparent;border:1px solid #2a3140;color:#8a93a4;border-radius:6px;padding:3px 8px;font:11px/1 var(--ui);cursor:pointer}
  .md-copy:hover{color:#e7eaf0;border-color:#4a5568}
  .md-code pre{margin:0;padding:12px 14px;overflow-x:auto;tab-size:2}
  .md-code code{background:none;border:none;padding:0;font:12.5px/1.6 var(--mono);color:#d7dce8}
  .tok-kw{color:#c792ea}.tok-fn{color:#82aaff}.tok-str{color:#c3e88d}
  .tok-num{color:#f78c6c}.tok-cm{color:#66707d;font-style:italic}
  .tok-type{color:#ffcb6b}.tok-key{color:#f07178}.tok-attr{color:#ffcb6b}
  .tok-tag{color:#f07178}.tok-meta{color:#89ddff}.tok-add{color:#c3e88d}
  .tok-del{color:#f07178}
  `;

  if (typeof document !== "undefined" && !document.getElementById("sim-md-css")) {
    const style = document.createElement("style");
    style.id = "sim-md-css";
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  const api = { render, highlight, hydrate, esc };
  global.SimMD = api;
})(typeof window !== "undefined" ? window : globalThis);
