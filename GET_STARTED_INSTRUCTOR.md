# Getting started — for instructors

You run the simulator; your learners connect to it and do sessions. This guide
covers setup, creating sessions, assigning scenarios and levels, and reviewing
runs. It takes ~15 minutes the first time.

---

## 1. Set up (same as a learner, plus a real model)

Follow **[GET_STARTED_STUDENT.md](GET_STARTED_STUDENT.md)** §2–§5 to get the code,
run `./setup.sh` (or `setup.ps1` on Windows), install Docker, and pick a model.

For real teaching you'll want **good persona quality**, so prefer either a
strong Ollama model, an **Anthropic API key**, or **Groq** (`LLM_PROVIDER=groq`, fast/cheap open models) over the default. A weak local
model can break character and give learners a misleading experience — see the
note in §6.

---

## 1b. Running for a whole class (one server, many learners)

To have learners connect to one machine instead of each running their own,
use the classroom server: `python serve.py` binds to your network and prints
the URLs to share; learners code locally and submit a patch. Full guide:
**[docs/CLASSROOM.md](docs/CLASSROOM.md)**.

## 2. Start the server

Use the command the preflight check suggested, e.g.:

```
source .venv/bin/activate         # Windows: .\.venv\Scripts\Activate.ps1
LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.1:8b ENV_PROVIDER=docker python -m uvicorn sim.app.main:app
```

To let learners on your network reach it, add `--host 0.0.0.0` and share your
machine's IP (e.g. `http://192.168.1.20:8000`). On the same machine, they use
`http://127.0.0.1:8000`.

---

## 3. Open the dashboard

Go to **http://127.0.0.1:8000/instructor** and enter the instructor password.
The default is `$T0mV13w`; change it by setting `INSTRUCTOR_PASSWORD` before you
start the server.

> **Honest note:** this password is a *light gate*, not real security — it's a
> shared secret sent in cleartext. Fine for a trusted classroom on a local
> machine; **not** for the open internet. See `docs/INSTRUCTOR.md`.

**First time** you'll be onboarded: pick the engineer level you'll most often
run. You can change it any time. You then land on **Overview**: session
counts, what needs review, a 14-day activity chart, and recent sessions.

On the hosted server there is no shared password: an admin creates your
instructor account and you sign in with email + password at `/login`. The
**Guide** button in the top bar opens the instructor onboarding guide.

---

## 4. Create a session for a learner

On the **New session** tab:

1. Pick a **scenario**. The list is grouped into **Product engineering**,
   **Systems design** and **Interview assessment**. Product scenarios are the
   original client-engagement runs (the learner builds in a dev box locally,
   or in a public repo they link when hosted: GitHub, or your own GitLab if
   the admin configured one). Systems design puts the
   learner in the **Systems Designer** seat: they talk through constraints,
   write `DESIGN.md` in the browser editor, submit it, and the AI team comes
   back with review questions and pushback. Interview assessment is a timed
   design interview with an interviewer and an assessor. Each scenario still
   shows a **difficulty** (intern → distinguished).
2. Pick the **engineer level** for this learner. A live indicator warns you if
   the scenario is pitched well above or below that level.
3. Click **Create session & get link**, then **Copy** the trainee link.
4. Send that link to the learner. When they open it, they get that exact
   scenario, and the pressure/personas/grading adapt to the level you chose.

For a whole class, use the **Cohort** tab instead: pick a cohort (an admin
builds them from a pasted roster), a scenario and a level, and **Create
sessions** makes one per member with a progress bar; **Copy all links** or
**Download CSV** hands them out. Hosted members also see their session on
their own dashboard.

The level changes three things: **pressure** (which stakeholders show up, and how
early), **persona posture** (patient mentor for juniors → terse, demanding for
seniors), and the **grading bar** (graded to that level's expectations).

---

## 5. Watch and review

On the **Sessions** tab you see every session you own with its scenario,
level, challenger, state (*not started*, *in progress*, *submitted*, *graded*
with the score), event count and last activity; search or filter by state and
scenario. Click one to open the **replay**:

- **Scrub or play** the timeline to watch the session unfold across every surface
  — chat, email, ticket moves, and the reveal/stakeholder moments.
- Filter by surface (Chat / Mail / Tickets / Signals) to focus.
- The **Design** panel draws the diagram the simulator made from the
  submitted `DESIGN.md`; **Refresh** re-reads it after a resubmission.
- Click **Grade** for a per-criterion score with evidence, graded at that
  session's level. The grade is **saved**: reopening the replay shows it with
  when and by whom; **Regrade** replaces it, and a newer submission drops the
  session back to *submitted* so you know to look again.
- **Interview assessment** scenarios (`Interview assessment` in New session)
  are timed system-design interviews: clarifying questions, a written design,
  then an assessor defense. Tickets are extra credit — toggle them on the
  grader. **Export** downloads a markdown audit (transcript, scores, Q&A,
  design, mermaid diagram) you can keep as a defensible record.

---

## 6. Two things to know before you trust it

1. **Use a strong model for real sessions.** Persona quality is what you're
   teaching against. If personas break character on a small local model, that's
   the model, not the design — retry on Anthropic or a larger model before
   drawing conclusions.

2. **The grade is directional, not calibrated — yet.** The grader adjusts to
   each level's expectations, but it has **not** been checked against real
   instructor scores, so it flies a `calibrated:false` flag. Treat scores as a
   discussion starter, not a verdict. To calibrate it, collect real
   human-scored runs and run the calibration harness — see
   `docs/PLAYTEST.md` and `README.md` (Calibrating the grader). This is the one
   step that turns a score into a grade you'd stand behind.

---

## 7. Settings and scenarios

The **Settings** tab lets you change the default level, browse the scenario
library (starter repo URLs for hosted build scenarios), or reset onboarding.
Admins have more under `/admin` → Settings: sign-up on/off, the grader's
calibrated flag, an announcement banner for challengers, and a read-only
deployment panel (model, classroom keys, repo hosts and the Connect apps;
`docs/REPO-HOSTS.md`). New scenarios are just files under
`sim/scenarios/<name>/scenario.yaml` — drop one in and it appears automatically
(see the existing scenarios as templates; the `iv_*` set is generated by
`tools/write_interview_scenarios.py`).
