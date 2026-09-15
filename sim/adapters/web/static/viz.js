/* SimViz: small inline-SVG charts for the dashboards. No library.
   Marks follow one spec: thin bars (<= 24px) with a 4px rounded data-end and a
   square baseline, hairline grid, text in the page's own ink, one axis.

     SimViz.tiles(items)                       -> html: stat tiles [{label, value, sub, tone}]
     SimViz.hbars(items, opts)                 -> html: horizontal bars [{label, value, sub, parts?}]
     SimViz.columns(series, opts)              -> html: daily columns [{day, value}] with hover titles
     SimViz.meter(value, total, label)         -> html: a coverage meter
     SimViz.legend(entries)                    -> html: [{label, color}]
   Colors are the validated dark-surface slots: blue #3987e5, aqua #199e70, yellow #c98500.
*/
window.SimViz = (function () {
  const C = { s1: "#3987e5", s2: "#199e70", s3: "#c98500", muted: "#5c6575" };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const CSS = `
  .viz-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 18px}
  .viz-tile{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;min-width:0}
  .viz-tile .l{font:600 11px/1 var(--ui);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
  .viz-tile .v{font:600 30px/1 var(--ui);color:var(--text);font-variant-numeric:tabular-nums;letter-spacing:-.01em}
  .viz-tile .s{font-size:12px;color:var(--muted);margin-top:6px}
  .viz-tile.good .v{color:#37d67a}.viz-tile.warn .v{color:#e0a94a}
  .viz-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;min-width:0}
  .viz-card h3{margin:0 0 2px;font-size:14px;font-weight:600;color:var(--text)}
  .viz-card .sub{font-size:12px;color:var(--muted);margin:0 0 12px}
  .viz-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-bottom:18px}
  .viz-hb{display:flex;flex-direction:column;gap:7px}
  .viz-hb .r{display:grid;grid-template-columns:minmax(120px,38%) 1fr auto;gap:10px;align-items:center;font-size:13px}
  .viz-hb .r .lab{color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .viz-hb .r .lab small{display:block;color:var(--muted);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .viz-hb .r .n{font:600 12.5px var(--mono);color:var(--muted);font-variant-numeric:tabular-nums;min-width:28px;text-align:right}
  .viz-hb svg{display:block;width:100%;height:14px;overflow:visible}
  .viz-empty{color:var(--muted);font-size:13px;padding:8px 0}
  .viz-cols svg{display:block;width:100%;height:120px;overflow:visible}
  .viz-cols .axis{display:flex;justify-content:space-between;font:11px var(--mono);color:var(--muted);margin-top:6px}
  .viz-meter{margin:8px 0}
  .viz-meter .lab{display:flex;justify-content:space-between;font-size:13px;color:var(--text);margin-bottom:5px}
  .viz-meter .lab b{font-variant-numeric:tabular-nums;color:var(--muted);font-weight:500}
  .viz-meter .track{height:8px;background:var(--panel-2);border:1px solid var(--line);border-radius:999px;overflow:hidden}
  .viz-meter .track i{display:block;height:100%;background:${C.s1};border-radius:0 4px 4px 0}
  .viz-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:10px}
  .viz-legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
  `;
  function css() {
    if (document.getElementById("sim-viz-css")) return;
    const s = document.createElement("style"); s.id = "sim-viz-css"; s.textContent = CSS; document.head.appendChild(s);
  }

  function tiles(items) {
    css();
    return `<div class="viz-tiles">${items.map(t =>
      `<div class="viz-tile ${t.tone || ""}"><div class="l">${esc(t.label)}</div><div class="v">${esc(t.value)}</div>${t.sub ? `<div class="s">${esc(t.sub)}</div>` : ""}</div>`).join("")}</div>`;
  }

  // one bar per row; `parts` (optional) stacks segments [{value,color,label}] with a 2px surface gap
  function hbars(items, opts) {
    css(); opts = opts || {};
    if (!items || !items.length) return `<div class="viz-empty">${esc(opts.empty || "Nothing yet.")}</div>`;
    const max = Math.max(1, ...items.map(i => i.value || 0));
    const W = 100, H = 14, T = 12;
    return `<div class="viz-hb">${items.map(i => {
      let svg;
      if (i.parts && i.parts.length) {
        let x = 0; const segs = [];
        i.parts.forEach((p, k) => {
          if (!p.value) return;
          const w = (p.value / max) * W;
          segs.push(`<rect x="${x.toFixed(2)}" y="1" width="${Math.max(0, w - (k ? 0.4 : 0)).toFixed(2)}" height="${T}" fill="${p.color}"><title>${esc(p.label)}: ${p.value}</title></rect>`);
          x += w;
        });
        svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${segs.join("")}</svg>`;
      } else {
        const w = ((i.value || 0) / max) * W;
        svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><rect x="0" y="1" width="${w.toFixed(2)}" height="${T}" rx="0" fill="${i.color || C.s1}"><title>${esc(i.label)}: ${i.value}</title></rect></svg>`;
      }
      return `<div class="r"><span class="lab" title="${esc(i.label)}">${esc(i.label)}${i.sub ? `<small>${esc(i.sub)}</small>` : ""}</span>${svg}<span class="n">${i.value}</span></div>`;
    }).join("")}</div>`;
  }

  // daily columns; series = [{day: "2026-09-15", value: n}], newest last
  function columns(series, opts) {
    css(); opts = opts || {};
    const n = series.length; if (!n) return `<div class="viz-empty">No activity yet.</div>`;
    const W = 420, H = 110, pad = 4, gap = 3;
    const max = Math.max(1, ...series.map(s => s.value || 0));
    const bw = Math.min(24, (W - pad * 2 - gap * (n - 1)) / n);
    const totalW = bw * n + gap * (n - 1), x0 = (W - totalW) / 2;
    const grid = [0.5, 1].map(f => `<line x1="0" x2="${W}" y1="${(H - 18 - (H - 26) * f).toFixed(1)}" y2="${(H - 18 - (H - 26) * f).toFixed(1)}" stroke="var(--line)" stroke-width="1"/>`).join("");
    const bars = series.map((s, i) => {
      const h = ((s.value || 0) / max) * (H - 26);
      const x = x0 + i * (bw + gap), y = H - 18 - h;
      const d = new Date(s.day + "T00:00:00");
      const label = d.toLocaleDateString([], { month: "short", day: "numeric" });
      return `<g><rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" fill="${opts.color || C.s1}"><title>${label}: ${s.value} ${esc(opts.unit || "")}</title></rect>` +
        (s.value && (i === n - 1 || s.value === max) ? `<text x="${(x + bw / 2).toFixed(1)}" y="${(y - 4).toFixed(1)}" text-anchor="middle" font-size="10" fill="var(--muted)">${s.value}</text>` : "") + `</g>`;
    }).join("");
    const first = new Date(series[0].day + "T00:00:00").toLocaleDateString([], { month: "short", day: "numeric" });
    const last = new Date(series[n - 1].day + "T00:00:00").toLocaleDateString([], { month: "short", day: "numeric" });
    return `<div class="viz-cols"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${grid}<line x1="0" x2="${W}" y1="${H - 18}" y2="${H - 18}" stroke="var(--line)" stroke-width="1"/>${bars}</svg><div class="axis"><span>${first}</span><span>${last} (today)</span></div></div>`;
  }

  function meter(value, total, label) {
    css();
    const pct = total ? Math.round((value / total) * 100) : 0;
    return `<div class="viz-meter"><div class="lab"><span>${esc(label)}</span><b>${value} / ${total} · ${pct}%</b></div><div class="track"><i style="width:${pct}%"></i></div></div>`;
  }

  function legend(entries) {
    css();
    return `<div class="viz-legend">${entries.map(e => `<span><i style="background:${e.color}"></i>${esc(e.label)}</span>`).join("")}</div>`;
  }

  function card(title, sub, body) {
    css();
    return `<div class="viz-card"><h3>${esc(title)}</h3>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}${body}</div>`;
  }

  return { tiles, hbars, columns, meter, legend, card, colors: C };
})();
