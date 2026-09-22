# Instructor replay view

The "flight recorder": watch a finished session back across every surface — chat,
email, ticket moves, reveals, the stakeholder beats — and grade it against the
evidence. This is the "go back and see exactly where you nailed it and where you
went wrong" from the pitch.

## Access
Locally, open **`/instructor`** (e.g. http://127.0.0.1:8000/instructor) and
enter the instructor password. Default: `$T0mV13w`. Override it:

```
set INSTRUCTOR_PASSWORD=your-password&& python -m uvicorn sim.app.main:app
```

> **This is a light gate, not real authentication.** The password is a single
> shared secret, visible to anyone with the code, and sent in cleartext over
> plain HTTP. It keeps trainees out of the replay on a trusted local machine —
> nothing more. Before exposing this to a network or untrusted users, put it
> behind real auth (accounts, HTTPS, per-user sessions). The check lives in one
> place (`create_web_app`), so swapping in real auth is contained.

Hosted (`AUTH_MODE=firebase`), there is no shared password: an admin creates
instructor accounts and you sign in at `/login`. Instructors see only the
sessions they own; admins see everything (`auth-plan.md`).

## The dashboard
After login, `/instructor` is a dashboard:
- **First run** shows an onboarding step — pick your default engineer level.
- **Overview** — counts (sessions, submitted, graded, in progress, not
  started), a 14-day activity chart, sessions by scenario and level, a
  *needs attention* list of submissions awaiting review, and recent sessions.
  Numbers are cached for about a minute; **Refresh** recounts.
- **New session** — pick a scenario (shown with its difficulty) and an engineer
  level, with a match warning if they're mismatched; optionally assign it to a
  challenger by email; create the session and copy the trainee link.
- **Cohort** — one session per cohort member on one scenario and level, with a
  progress bar; copy all links or download a CSV.
- **Sessions** — every session you own with challenger, state and grade;
  search and filter; click to replay.
- **Settings** — change the default level, set starter repo URLs for hosted
  build scenarios, or reset onboarding.

## What you can do (replay)
- **Pick a session** — every recorded run is listed with its event count and last activity.
- **Scrub / play the timeline** — step through or auto-play the session as it
  unfolded. Filter by surface (Chat / Mail / Tickets / Signals) to focus.
- **Read the signals** — reveals ("Priya opened up"), joins, and inbound emails
  are shown as a distinct class, so you can see *when* discovery happened.
- **Design** — the diagram drawn from the submitted `DESIGN.md` (and any
  ```mermaid block in the transcript is drawn inline).
- **Grade** — runs the grader on the full transcript (which includes email and
  ticket actions), the submitted design, its diagram and, if toggled, the
  tickets, and shows the per-criterion score with evidence, plus the
  `calibrated:false` caveat until an admin flips the flag. The grade is stored:
  reopening the replay shows it with when and by whom, **Regrade** replaces
  it, and **Export** downloads a markdown audit using the stored grade.

Because everything a session produces is already recorded in the transcript, the
replay is a pure read-over-data view — it needs no new capture.
