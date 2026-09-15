SimApps.register({
  id: "submit",
  title: "Submit",
  accent: "#37d67a",
  icon: '<svg viewBox="0 0 24 24"><path d="M12 4v11" stroke-linecap="round"/><path d="M7 9l5-5 5 5" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 19h16" stroke-linecap="round"/></svg>',
  css: `
  .sub{height:100%;overflow-y:auto;padding:22px 26px;max-width:760px;margin:0 auto}
  .sub h2{margin:0 0 4px;font-size:17px}
  .sub p{color:var(--muted);font-size:13px;margin:0 0 14px;line-height:1.55}
  .sub .step{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px}
  .sub .step h3{margin:0 0 8px;font-size:14px}
  .sub .cmd{background:var(--ink);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:12.5px/1.6 var(--mono);color:var(--sig);white-space:pre-wrap;user-select:all}
  .sub button{border-radius:9px;padding:9px 14px;font:inherit;font-size:13px;cursor:pointer;border:1px solid var(--line);background:var(--panel-2);color:var(--text)}
  .sub button.primary{background:var(--me);border-color:var(--me);color:#fff;font-weight:600}
  .sub button:disabled{opacity:.5;cursor:default}
  .sub textarea{width:100%;min-height:150px;background:var(--ink);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:11px 13px;font:12.5px/1.5 var(--mono);outline:none;resize:vertical}
  .sub textarea:focus{border-color:var(--me)}
  .sub .row{display:flex;gap:10px;align-items:center;margin-top:10px;flex-wrap:wrap}
  .sub .ok{color:var(--ok,#37d67a);font-size:13px}
  .sub .bad{color:#e5807a;font-size:13px}
  .sub .hist{font-size:13px;color:var(--muted)}
  .sub .hist .it{padding:6px 0;border-bottom:1px solid var(--line);font-family:var(--mono)}
  .sub details{margin-top:6px}
  .sub summary{cursor:pointer;color:var(--muted);font-size:13px}
  .sub .mono{font-family:var(--mono);word-break:break-all}
  `,
  mount(root, ctx) {
    const sid = ctx.sid;
    const wf = (ctx.scenario && ctx.scenario.workflow) || { kind: "sandbox", submit_label: "Submit", submit_hint: "" };
    const esc = s => { const d = document.createElement("div"); d.textContent = s || ""; return d.innerHTML; };
    const api = (p, o) => fetch(`/api/session/${sid}${p}`, o);
    const post = async (p, body) => (await api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })).json();

    const intro = {
      doc: `Write DESIGN.md in the <b>Files</b> app. When it says what you mean, submit it here —
            the team reads exactly what is in your workspace right now.`,
      sandbox: `Build in your workspace (Files app, or your own editor on the folder). Commit as you go.
            Submitting snapshots the workspace and hands it to the reviewers.`,
      repo: `Push your work to the public GitHub repo you linked in the <b>Workspace</b> app,
            then submit. Grading reads your commits and files from GitHub.`,
    }[wf.kind] || "";

    root.innerHTML = `<div class="sub">
      <h2>Submit your work</h2>
      <p>${intro}</p>
      <div class="step" id="main">
        <h3>${esc(wf.submit_label || "Submit")}</h3>
        <p>${esc(wf.submit_hint || "")}</p>
        <div id="repo-line"></div>
        <div class="row">
          <button class="primary" id="go">${esc(wf.submit_label || "Submit")}</button>
          <span id="status"></span>
        </div>
      </div>
      ${wf.kind === "sandbox" ? `
      <details class="step">
        <summary>Offline fallback: work outside the workspace and submit a patch</summary>
        <p style="margin-top:10px">Download the starter, work locally, then paste a git patch of your changes.</p>
        <div class="row"><button id="dl">Download starter code (.zip)</button></div>
        <div class="cmd" style="margin-top:10px">unzip ${esc(sid)}-starter.zip -d my-project
cd my-project
git init && git add -A && git commit -m "starting point"
# …do the work, committing as you go…
git format-patch --stdout HEAD~999..HEAD > work.patch     # or:  git diff > work.patch</div>
        <textarea id="patch" style="margin-top:10px" placeholder="Paste your git patch / diff here…"></textarea>
        <div class="row">
          <input type="file" id="file" accept=".patch,.diff,.txt"/>
          <button id="send">Submit patch</button>
          <span id="pstatus"></span>
        </div>
      </details>` : ""}
      <div class="step">
        <h3>Submission history</h3>
        <div class="hist" id="hist">—</div>
      </div>
    </div>`;
    const q = s => root.querySelector(s);
    const status = q("#status");

    async function showRepoLine() {
      if (wf.kind !== "repo") return;
      let url = "";
      try { url = (await (await api(`/workspace/repo`)).json()).url || ""; } catch (e) {}
      q("#repo-line").innerHTML = url
        ? `<div class="row" style="margin:0 0 6px"><span style="color:var(--muted)">Linked repo:</span><span class="mono">${esc(url)}</span></div>`
        : `<div class="bad" style="margin-bottom:6px">No repo linked yet — <a href="#" id="tows" style="color:var(--me)">open Workspace</a> to link it.</div>`;
      const a = q("#tows"); if (a) a.onclick = e => { e.preventDefault(); SimApps.open("workspace"); };
      q("#go").disabled = !url;
    }

    q("#go").onclick = async () => {
      q("#go").disabled = true; status.textContent = "Submitting…";
      let r;
      try {
        r = wf.kind === "doc" ? await post(`/submit-doc`)
          : wf.kind === "repo" ? await post(`/submit-repo`, {})
          : await post(`/submit-workspace`);
      } catch (e) { r = { error: "Could not reach the server." }; }
      q("#go").disabled = false;
      if (r.error) { status.innerHTML = `<span class="bad">${esc(r.error)}</span>`; return; }
      const after = wf.kind === "doc" ? "Head to Team Chat — the review starts there." : "Grade the run in Team Chat.";
      status.innerHTML = `<span class="ok">✓ Submitted${r.lines ? ` (${r.lines} lines)` : ""}${r.message ? ` — ${esc(r.message)}` : ""}. ${after}</span>`;
      loadHist();
    };

    if (wf.kind === "sandbox") {
      q("#dl").onclick = () => { window.location = `/api/session/${sid}/starter.zip`; };
      q("#file").onchange = e => {
        const f = e.target.files[0]; if (!f) return;
        const r = new FileReader(); r.onload = () => { q("#patch").value = r.result; }; r.readAsText(f);
      };
      q("#send").onclick = async () => {
        const content = q("#patch").value.trim();
        if (!content) { q("#pstatus").innerHTML = `<span class="bad">Nothing to submit yet.</span>`; return; }
        const filename = (q("#file").files[0] || {}).name || "work.patch";
        q("#pstatus").textContent = "Submitting…";
        const r = await post(`/submit`, { filename, content });
        if (r.error) { q("#pstatus").innerHTML = `<span class="bad">${esc(r.error)}</span>`; return; }
        q("#pstatus").innerHTML = `<span class="ok">✓ Submitted (${r.lines} lines). Grade the run in Team Chat.</span>`;
        loadHist();
      };
    }

    async function loadHist() {
      let data;
      try { data = await (await api(`/submissions`)).json(); } catch (e) { return; }
      const box = q("#hist");
      if (!data.submissions || !data.submissions.length) { box.textContent = "No submissions yet."; return; }
      box.innerHTML = data.submissions.map(s =>
        `<div class="it">#${s.seq}  ${esc(s.kind === "repo" ? s.content : s.filename)}  ${s.kind === "repo" ? "" : `(${s.lines} lines)`}  ${new Date(s.ts).toLocaleString()}</div>`).join("");
    }
    showRepoLine(); loadHist();
    return { unmount() {} };
  }
});
