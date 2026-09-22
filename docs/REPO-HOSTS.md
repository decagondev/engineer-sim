# Repo hosts: GitHub and a self-hosted GitLab

Build scenarios on the hosted server use the **repo** workflow: the learner forks a
starter, pushes from their own machine, and links their public repo in the Workspace
app. The simulator then browses it in Files, reads the commits for grading, and, once
the learner has *connected* their account, lets Files commit straight to the repo.

This works for **GitHub** and for **one GitLab instance** (for example
`https://labs.gauntletai.com`). A link is routed to the right host by its domain; the
learner never has to say which one they used.

## What each host gives you

| | GitHub | GitLab instance |
|---|---|---|
| Enabled by | always on | `GITLAB_URL` |
| Anonymous reads | public repos, ~60 calls/hour per IP | public projects, instance rate limit |
| Classroom token | `GITHUB_TOKEN` (no scopes) | `GITLAB_TOKEN` (`read_api`) |
| Personal token | Settings → GitHub token (no scopes) | Settings → GitLab token (`read_api`) |
| Connect (browser commits) | `GITHUB_OAUTH_CLIENT_ID`, scope `public_repo` | `GITLAB_OAUTH_CLIENT_ID`, scope `api` |
| Token lifetime | does not expire | 2 hours; refreshed automatically with the refresh token |
| Fork detection for "net changes" | `parent` of a fork | `forked_from_project` |
| Starter link looks like | `https://github.com/org/starter` | `https://labs.gauntletai.com/group/starter` |

The classroom token is used when a learner has no token of their own. It only ever
reads. **Never give the classroom token a write scope**: the app does not need it, and a
token that can write is a liability on a shared server.

## Environment variables

```
GITHUB_TOKEN=ghp_...                     # optional; classroom read limit for GitHub
GITHUB_OAUTH_CLIENT_ID=Iv1...            # optional; enables Connect GitHub

GITLAB_URL=https://labs.gauntletai.com   # optional; enables the GitLab host
GITLAB_TOKEN=glpat-...                   # optional; classroom read_api token for that instance
GITLAB_OAUTH_CLIENT_ID=<application id>  # optional; enables Connect GitLab
BYOK_SECRET=...                          # required before anyone stores a token (Fernet key)
```

`/health` reports `github_oauth`, `gitlab_url` and `gitlab_oauth`; the admin dashboard's
Settings → Deployment panel shows the same plus whether each classroom token is set.

## Creating the GitHub OAuth app (Connect GitHub)

1. On GitHub: your avatar → **Settings** → **Developer settings** → **OAuth Apps** →
   **New OAuth App**. An organisation can own it instead (organisation Settings →
   Developer settings).
2. Fill in a name, the homepage (`https://worksim.decadev.co.uk`) and any callback URL
   (the device flow never redirects, but the field is required).
3. Tick **Enable Device Flow**. Without it, Connect GitHub fails with "device flow
   disabled".
4. Register, copy the **Client ID**, and set it as `GITHUB_OAUTH_CLIENT_ID`. No client
   secret is needed.

Learners press **Connect GitHub** in the Workspace app, enter the code at
`github.com/login/device`, and approve. The token is stored encrypted with the
`public_repo` scope; that is what unlocks Files writes for that person.

## Creating the GitLab OAuth application (Connect GitLab)

Device-flow sign-in needs **GitLab 17.2 or newer**. Browsing, grading and pasted read
tokens work on older versions too.

1. Sign in to the instance as an administrator and open **Admin Area** (wrench icon) →
   **Applications** → **New application**. (A personal app under avatar → Preferences →
   Applications also works, but it disappears with that account.)
2. Fill it in:
   - **Name:** Engineering Flight Simulator
   - **Redirect URI:** required by the form, unused by the device flow. Use the server's
     URL, e.g. `https://worksim.decadev.co.uk/`.
   - **Confidential:** **untick**. The device grant is only allowed for non-confidential
     applications, and the server never holds a client secret.
   - **Scopes:** tick **`api`**. It is the only scope that lets the REST file API commit.
     `read_api` would let people connect but leave Files read-only.
3. Save and copy the **Application ID** into `GITLAB_OAUTH_CLIENT_ID`. Ignore the secret.
4. Set `GITLAB_URL` to the instance's root URL (no trailing slash) and redeploy.

Learners press **Connect GitLab**, approve on the instance's `/oauth/device` page, and
Files becomes an editor for projects on that host. GitLab access tokens expire after two
hours; the server stores the refresh token alongside and renews the access token before
it lapses, so a connection lasts as long as the refresh token does. If a renewal ever
fails the learner just presses Connect again.

## Publishing starters on GitLab

The steps in `docs/PUBLISH-SCENARIOS.md` apply unchanged: create a **public** project on
the instance, push the starter folder to it, paste the project URL into the scenario
library. Learners fork it on the instance; forks keep the `forked_from_project` link, so
the grader's "net changes vs starter" section works exactly as it does for GitHub forks.

Group projects are fine: `https://labs.gauntletai.com/cohort-7/agentforge` has the
namespace `cohort-7` and the project `agentforge`; nested groups work too.

## What learners see

- **Workspace app:** the starter link, the clone commands for whichever host it lives on,
  the link box (accepts a GitHub URL or a project URL on the configured instance), and one
  **Connect** card per available host.
- **Files app:** read-only until connected, then Save commits with the message
  `Edit <path> from the workstation`. **Refresh** re-reads the default branch tip.
  **What changed** shows the net diff against the fork parent.
- **Settings (challenger dashboard):** GitHub token card, and a GitLab token card once the
  server has a `GITLAB_URL`. Pasted tokens are read-only by design; only Connect unlocks
  writes.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "that doesn't look like a repo URL on github.com or labs.gauntletai.com" | link is on another host | set `GITLAB_URL` for that host, or use one of the listed ones |
| "project not found: check the URL, and make sure the project is public" | private project, or a typo | make it public, or connect / paste a token that can read it |
| "GitLab wants a sign-in for that" | 401 from the instance | same as above |
| Connect GitLab says "unsupported grant type" | GitLab older than 17.2 | upgrade the instance; browsing still works |
| Connect GitLab says `invalid_client` | wrong Application ID, or Confidential left ticked | check the application in the Admin Area |
| Connect GitHub says device flow disabled | the OAuth app has Device Flow unticked | tick it in the app settings |
| Files is read-only after connecting on GitLab | app created with `read_api` only | recreate it with `api`; learners reconnect |
| Rate-limit errors on a class day | everyone on the anonymous bucket | set the classroom token, ask learners to add their own |

## Where the code lives

`sim/core/ports/repo_host.py` is the port. `sim/adapters/build/github_host.py` and
`sim/adapters/build/gitlab_api.py` are the two adapters; `sim/adapters/build/host_router.py`
chooses by URL. `sim/adapters/auth/github_oauth.py` and `gitlab_oauth.py` are the device
flows; `sim/adapters/auth/gitlab_tokens.py` handles GitLab token expiry. Wiring is
`_build_repo_hosts` in `sim/app/composition_root.py`. Tests:
`tests/regression/test_gitlab.py`, `test_github_connect.py`, `test_repo_workspace.py`.
