# Publishing scenario starters (for instructors)

Each scenario ships with a starter folder in this repo. To use the repo
submission mode, you turn each one into a **public** repo once, on GitHub or on
your class's GitLab instance (when the admin has configured one; see
`docs/REPO-HOSTS.md`), then paste its URL into your instructor dashboard.
Learners fork that repo, do the work, push, and link their own repo URL. No
scripts, no tokens — just the steps below.

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

**On a GitLab instance** the steps are the same: **New project** → blank, public,
no README; push the starter folder to it; copy the project URL
(e.g. `https://labs.gauntletai.com/<group>/flightsim-churn-dashboard`). Learners
use **Fork** on the project page; forks keep their link to the starter, which is
what gives the grader the "net changes vs starter" section.

## Tell the simulator about it

1. Open the instructor dashboard (`/instructor`) → **Settings**.
2. Each scenario has a **starter repo URL** field. Paste the URL and click **Save**.

That's it. From then on, when a learner opens a hosted session for that scenario,
the **Workspace** app shows them the starter link to fork; they paste their own
public repo URL there once, browse what they pushed in **Files** (with a Refresh
button), and press **Submit for grading** in **Submit**. If they **Connect
GitHub** or **Connect GitLab** in Workspace, Files becomes an editor for that
repo and every Save is a commit; otherwise it stays read-only and they push from
their machine.

Design scenarios (`sys_*`, `iv_*`) never use a repo: learners write `DESIGN.md`
in the browser and submit it from the workspace, on every deployment.

## Notes

- **Public on purpose.** This mode is trust-based: learners' repos are public.
  If reused scenarios' solutions accumulate publicly, refresh the scenario
  rather than adding gates. (On a GitLab instance the classroom `GITLAB_TOKEN`
  can also read internal projects, if you would rather keep forks off the
  public internet.)
- **No starter URL set?** Hosted learners see "ask your instructor" in the
  Workspace app; only a local server offers the patch fallback (download the
  starter zip, work locally, submit a patch). `WORK_MODE=local|hosted` overrides
  the automatic choice.
- **Rate limits:** the simulator reads public repos via the host's API. For a
  class, set a `GITHUB_TOKEN` (a classic read-only token) when starting the server
  to raise the GitHub limit from ~60/hr to ~5000/hr, and a `read_api`
  `GITLAB_TOKEN` for the GitLab instance:
  `GITHUB_TOKEN=ghp_xxx python -m uvicorn sim.app.main:app`. Challengers can
  also store their own tokens in Settings, which spreads the load.
