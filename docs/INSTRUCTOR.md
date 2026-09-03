# Instructor replay view

The "flight recorder": watch a finished session back across every surface — chat,
email, ticket moves, reveals, the stakeholder beats — and grade it against the
evidence. This is the "go back and see exactly where you nailed it and where you
went wrong" from the pitch.

## Access
Open **`/instructor`** (e.g. http://127.0.0.1:8000/instructor) and enter the
instructor password. Default: `$T0mV13w`. Override it:

```
set INSTRUCTOR_PASSWORD=your-password&& python -m uvicorn sim.app.main:app
```

> **This is a light gate, not real authentication.** The password is a single
> shared secret, visible to anyone with the code, and sent in cleartext over
> plain HTTP. It keeps trainees out of the replay on a trusted local machine —
> nothing more. Before exposing this to a network or untrusted users, put it
> behind real auth (accounts, HTTPS, per-user sessions). The check lives in one
> place (`create_web_app`), so swapping in real auth is contained.

## The dashboard
After login, `/instructor` is a dashboard:
- **First run** shows an onboarding step — pick your default engineer level.
- **New session** — pick a scenario (shown with its difficulty) and an engineer
  level, with a match warning if they're mismatched; create the session and copy
  the trainee link to hand over.
- **Sessions** — every recorded run with its scenario + level; click to replay.
- **Settings** — change the default level, browse the scenario library, or reset
  onboarding.

## What you can do (replay)
- **Pick a session** — every recorded run is listed with its event count and last activity.
- **Scrub / play the timeline** — step through or auto-play the session as it
  unfolded. Filter by surface (Chat / Mail / Tickets / Signals) to focus.
- **Read the signals** — reveals ("Priya opened up"), joins, and inbound emails
  are shown as a distinct class, so you can see *when* discovery happened.
- **Grade** — runs the grader on the full transcript (which includes email and
  ticket actions) and shows the per-criterion score with evidence, plus the
  `calibrated:false` caveat until you've run calibration.

Because everything a session produces is already recorded in the transcript, the
replay is a pure read-over-data view — it needs no new capture.
