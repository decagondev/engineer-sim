# Publishing scenario starters to GitHub (for instructors)

Each scenario ships with a starter folder in this repo. To use the GitHub
submission mode, you turn each one into a **public** GitHub repo once, then paste
its URL into your instructor dashboard. Learners fork that repo, do the work,
push, and submit their own repo URL. No scripts, no tokens — just the steps below.

## Where the starters live

```
sim/scenarios/<scenario>/starter/
```
For example:
- `sim/scenarios/churn_dashboard/starter/`
- `sim/scenarios/support_copilot/starter/`
- `sim/scenarios/intern_signup/starter/`  … and so on for every product scenario.
- Systems design (doc-first): `sys_shortlink`, `sys_notify`, `sys_collab`,
  `sys_apigw`, `sys_feed` — same `starter/` layout; learners submit `DESIGN.md`.
- Interview assessment (`iv_*`): timed system-design interviews. Learners ask
  the interviewer clarifying questions, submit `DESIGN.md`, then defend it with
  an assessor. Extra-credit tickets live in `TICKETS.md`.

## Turn a starter folder into a public repo (once per scenario)

1. On https://github.com, create a **new, empty, public** repository — e.g.
   `flightsim-churn-dashboard`. Don't add a README/licence (the starter has its own).
2. On your machine, from inside the starter folder, push it up:

   **macOS / Linux:**
   ```
   cd sim/scenarios/churn_dashboard/starter
   git init && git add -A && git commit -m "starter"
   git branch -M main
   git remote add origin https://github.com/<you>/flightsim-churn-dashboard.git
   git push -u origin main
   ```
   **Windows (PowerShell):** the same commands work.

3. *(Recommended)* On the repo's GitHub page → **Settings** → tick
   **Template repository**. That gives learners a clean "Use this template"
   button instead of a fork, with no shared history to trip over.

4. Copy the repo URL (e.g. `https://github.com/<you>/flightsim-churn-dashboard`).

Repeat for each scenario you want to run. GitHub Free covers unlimited public
repos at no cost.

## Tell the simulator about it

1. Open the instructor dashboard (`/instructor`) → **Settings**.
2. Each scenario has a **starter repo URL** field. Paste the URL and click **Save**.

That's it. From then on, when a learner opens a session for that scenario, the
**Submit** app shows them the starter link to fork, and they submit their own
public repo URL back for grading.

## Notes

- **Public on purpose.** This mode is trust-based (see `SUBMISSION-VIA-GITHUB.md`):
  learners' repos are public. If reused scenarios' solutions accumulate publicly,
  refresh the scenario rather than adding gates.
- **No starter URL set?** Learners fall back to the **patch** flow (download the
  starter zip, work locally, submit a patch) — that path needs no GitHub.
- **Rate limits:** the simulator reads public repos via the GitHub API. For a
  class, set a `GITHUB_TOKEN` (a classic read-only token) when starting the server
  to raise the API limit from ~60/hr to ~5000/hr:
  `GITHUB_TOKEN=ghp_xxx python -m uvicorn sim.app.main:app`.
