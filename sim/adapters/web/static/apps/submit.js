SimApps.register({
  id: "submit",
  title: "Submit",
  accent: "#37d67a",
  icon: '<svg viewBox="0 0 24 24"><path d="M12 4v11" stroke-linecap="round"/><path d="M7 9l5-5 5 5" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 19h16" stroke-linecap="round"/></svg>',
  css: `
  .sub{height:100%;overflow-y:auto;padding:22px 26px;max-width:760px;margin:0 auto}
  .sub h2{margin:0 0 4px;font-size:17px}
  .sub p{color:var(--muted);font-size:13px;margin:0 0 14px}
  .sub .step{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px}
  .sub .step h3{margin:0 0 8px;font-size:14px}
  .sub .cmd{background:var(--ink);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:12.5px/1.6 var(--mono);color:var(--sig);white-space:pre-wrap;user-select:all}
  .sub button{border-radius:9px;padding:9px 14px;font:inherit;font-size:13px;cursor:pointer;border:1px solid var(--line);background:var(--panel-2);color:var(--text)}
  .sub button.primary{background:var(--me);border-color:var(--me);color:#fff;font-weight:600}
  .sub textarea{width:100%;min-height:150px;background:var(--ink);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:11px 13px;font:12.5px/1.5 var(--mono);outline:none;resize:vertical}
  .sub textarea:focus{border-color:var(--me)}
  .sub .row{display:flex;gap:10px;align-items:center;margin-top:10px;flex-wrap:wrap}
  .sub .ok{color:var(--ok);font-size:13px}
  .sub .hist{font-size:13px;color:var(--muted)}
  .sub .hist .it{padding:6px 0;border-bottom:1px solid var(--line);font-family:var(--mono)}
  `,
  mount(root, ctx) {
    const sid = ctx.sid;
    root.innerHTML = `<div class="sub">
      <h2>Submit your work</h2>
      <p>You're working on your own machine. Here's how to get the starter code,
         and how to hand your work back for review.</p>

      <div class="step">
        <h3>1 · Get the starter code</h3>
        <p>Download it, unzip somewhere, and start a git repo so your history is captured.</p>
        <div class="row"><button class="primary" id="dl">Download starter code (.zip)</button></div>
        <div class="cmd" style="margin-top:10px">unzip ${sid}-starter.zip -d my-project
cd my-project
git init && git add -A && git commit -m "starting point"</div>
      </div>

      <div class="step">
        <h3>2 · Build it (in your own editor / coding tool)</h3>
        <p>Do the work. Commit as you go — commits are part of how it's reviewed.</p>
      </div>

      <div class="step">
        <h3>3 · Make a patch of your changes</h3>
        <p>From your project folder, create a patch of everything you did since the start:</p>
        <div class="cmd">git add -A
git commit -m "my work"
git format-patch --stdout HEAD~999..HEAD > work.patch     # or:  git diff > work.patch</div>
      </div>

      <div class="step">
        <h3>4 · Submit it</h3>
        <p>Open <code>work.patch</code>, paste its contents here (or choose the file), then submit.</p>
        <textarea id="patch" placeholder="Paste your git patch / diff here…"></textarea>
        <div class="row">
          <input type="file" id="file" accept=".patch,.diff,.txt"/>
          <button class="primary" id="send">Submit work</button>
          <span id="status"></span>
        </div>
      </div>

      <div class="step">
        <h3>Submission history</h3>
        <div class="hist" id="hist">—</div>
      </div>
    </div>`;
    const q = s => root.querySelector(s);

    q("#dl").onclick = () => { window.location = `/api/session/${sid}/starter.zip`; };

    q("#file").onchange = e => {
      const f = e.target.files[0]; if (!f) return;
      const r = new FileReader();
      r.onload = () => { q("#patch").value = r.result; };
      r.readAsText(f);
    };

    q("#send").onclick = async () => {
      const content = q("#patch").value.trim();
      if (!content) { q("#status").innerHTML = `<span style="color:var(--warn)">Nothing to submit yet.</span>`; return; }
      const filename = (q("#file").files[0] || {}).name || "work.patch";
      q("#status").textContent = "Submitting…";
      const r = await (await fetch(`/api/session/${sid}/submit`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, content }) })).json();
      if (r.error) { q("#status").innerHTML = `<span style="color:var(--bad)">${r.error}</span>`; return; }
      q("#status").innerHTML = `<span class="ok">✓ Submitted (${r.lines} lines). You can now Grade the run in Team Chat.</span>`;
      loadHist();
    };

    async function loadHist() {
      const data = await (await fetch(`/api/session/${sid}/submissions`)).json();
      const box = q("#hist");
      if (!data.submissions.length) { box.textContent = "No submissions yet."; return; }
      box.innerHTML = data.submissions.map(s =>
        `<div class="it">#${s.seq}  ${s.filename}  (${s.lines} lines)  ${new Date(s.ts).toLocaleString()}</div>`).join("");
    }
    loadHist();
    return { unmount() {} };
  }
});
