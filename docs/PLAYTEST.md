# Playtest Protocol — Engineering Flight Simulator

The test suite proves the machine *works*. This proves the machine is *worth
running*. It answers the questions code can't: do the personas feel real, does
discovery feel rewarding, does the pressure land, and does the grade feel fair to
a human who watched?

**Every session produces two things:** a qualitative read on the experience, and
one real human-scored transcript that becomes a `calibration/` fixture. That's
deliberate — playtesting and grader calibration are the same act.

---

## 0. What this playtest is and isn't

**Testing:** persona believability, productive vagueness, the reveal ladder, the
uninvited-stakeholder beat, whether discovery is observably measurable, whether
the grade feels valid, and UI friction.

**Not testing (out of scope, on purpose):**
- The containerized "real computer" — not built yet. Sessions are **plan-only**:
  the player does discovery + scoping + stakeholder handling + a written plan
  back in chat. That maps exactly onto the rubric, so nothing is lost.
- Statistical grader validity — that needs ≥10 scored transcripts. One playtest
  can't settle it; it can only *feed* it. Watch for gross mis-grades, don't
  render a verdict.

---

## 1. Roles

- **Player** — the engineer being simulated. Use someone who did **not** build
  this, so they come in cold like a real trainee. This matters most for the
  discovery test: a builder already knows the hidden need.
- **Facilitator** — you. Set up, observe silently, take timestamped notes, run
  the debrief. Do **not** help mid-session.
- **Blind scorer** — someone who scores the transcript against the rubric
  *without seeing the grader's output*. For the first runs this can be the
  facilitator; for real calibration validity you eventually want scorers who
  didn't build the grader. Their score is the human ground truth.

---

## 2. Setup (before the player arrives)

1. **Provider.** Use a **strong model** for the first playtests
   (`LLM_PROVIDER=anthropic ANTHROPIC_MODEL=<current>`). Persona quality is what
   you're testing — a weak local model breaking character would confound the
   result. If you must use Ollama, tag any character breaks as *possibly
   model-limited*, and don't blame the design until you've retried on a strong
   model.
2. **Scenario.** Start with `churn_dashboard` (the discovery-heavy flagship).
   `make run`, confirm http://127.0.0.1:8000 loads and both personas appear.
3. **Grader flag.** Leave `GRADER_CALIBRATED` unset — `/grade` should show
   `calibrated:false`. Good: the player and scorer should see the caveat, not a
   number dressed up as truth.
4. **Facilitator's do-not-reveal list.** Say none of this to the player:
   - that Priya has a hidden need (or what it is),
   - that there's a reveal ladder or that questions "unlock" things,
   - that Marcus will show up,
   - anything coaching them toward good questions during the run.

### The brief to read to the player (verbatim)

> "You're an engineer brought in to help Priya, Head of Customer Success at a
> ~40-person SaaS company. She's asked for some help. Talk to her, figure out
> what actually needs building, and come back with a short plan — what you'd
> build first and why. You've got about 25 minutes. There's no right answer key;
> work it like a real client. Type to whoever you want using the dropdown at the
> top. Go whenever you're ready."

That's it. No more. Under-briefing is the point.

---

## 3. Session run-of-show (~35 min total)

| Time | Step |
|---|---|
| 0:00 | Read the brief. Start a fresh session (note the session id from the URL/console). |
| 0:00–25:00 | Player works. Facilitator observes silently, timestamped notes against the hypotheses (§4). |
| 25:00 | Call time. Ask the player to post their final plan in chat if they haven't. |
| 25:00–30:00 | Player debrief (§6) — capture their words before they see any score. |
| 30:00 | Export the transcript, run the grader, fill the scoring sheet (§5), compare, save the fixture (§7). |

Run **one pilot with the facilitator as player first**, to shake out obvious
breakage (a persona derailing on the chosen model, a UI snag) before you spend a
fresh player on it.

---

## 4. Hypotheses (the spine — each is falsifiable)

Score each PASS / PARTIAL / FAIL in the sheet, with a one-line note.

| # | Hypothesis | Watch for | FAILS if |
|---|---|---|---|
| H1 | Priya is believably, *productively* vague | on-topic but under-specified opening replies | she dumps the real need immediately, or reads as robotic/incoherent |
| H2 | Anti-leak holds | a direct "just tell me what you need" gets deflected | she volunteers "churn / early-warning / at-risk" unprompted or on a lazy ask |
| H3 | Good discovery is rewarded | asking *who uses it / where's the data / what does at-risk mean* visibly opens her up | good questions don't unlock, or the conversation opens up at random |
| H4 | The uninvited stakeholder lands | Marcus's arrival changes the player's behavior (they defend scope) | it reads as a non-sequitur, or ignoring him has no felt consequence |
| H5 | Discovery is observably measurable | you can point to the exact moment the player found (or missed) the real need | it's murky whether they got it |
| H6 | The grade feels fair | having watched, you'd sign off on the grader's score ±0.15 and its evidence is real | it rewards the wrong things, or cites things that didn't happen |
| H7 | Low friction | attention goes to the problem, not the tool | confusion about who they're talking to, lag, lost/dropped messages |

---

## 5. Scoring sheet

Copy this per session. **Part A is the human ground-truth score** — use the same
four criteria and weights as the scenario so it's directly comparable to the
grader. **Part B is the experience read.**

### Part A — Rubric score (0.00–1.00, use the anchors)

Anchors are written for `churn_dashboard`. The real need = *proactive early
warning of at-risk accounts*; signals = *usage drop / downgrade / ticket spikes*;
data reality = *Postgres + Stripe, unjoined*; constraints = *~6 weeks, one
part-time eng, no daily manual ops*.

**discovery (weight 2.0)** — did they find the real need?
- `0.00` never probed; took "dashboard" at face value
- `0.25` asked generic questions but stayed inside the dashboard framing
- `0.50` sensed there's more; got partway (e.g. who uses it) but never named the early-warning need
- `0.75` uncovered the real need through questioning
- `1.00` uncovered it *and* the underlying signals and the data reality

**scoping (weight 1.5)** — is the plan shippable within the constraints?
- `0.00` no scope, or promised the moon
- `0.25` vague, or wildly over/under-scoped
- `0.50` reasonable but ignored a key constraint (deadline / part-time / data mess)
- `0.75` shippable within constraints; sensible MVP-first
- `1.00` crisp minimal first slice that proves value, explicit "then invest" path, all constraints respected

**stakeholders (weight 1.0)** — did they handle Marcus credibly?
- `0.00` ignored or dismissed him
- `0.25` acknowledged but hand-waved the maintenance concern
- `0.50` engaged but didn't resolve it
- `0.75` addressed maintenance/scope credibly
- `1.00` turned the concern into a better, low-ops plan

**communication (weight 1.0)** — clear to a non-technical audience?
- `0.00` unclear / jargon dump
- `0.50` understandable but not tailored to a non-technical reader
- `0.75` clear plan stated in outcome terms
- `1.00` crisp, non-technical, decision-ready summary

```
discovery      ____   evidence: _______________________________________
scoping        ____   evidence: _______________________________________
stakeholders   ____   evidence: _______________________________________
communication  ____   evidence: _______________________________________
```
> Weighted total is computed for you when you save the fixture; you only fill the
> four numbers + one evidence line each.

### Part B — Experience (1 = bad, 5 = great)

```
Believable as a real client (H1)          1  2  3  4  5
Stayed productively vague / no leak (H2)   1  2  3  4  5
Good questions felt rewarded (H3)          1  2  3  4  5
Stakeholder pressure felt real (H4)        1  2  3  4  5
Grade felt fair, given what I watched (H6) 1  2  3  4  5
Tool stayed out of the way (H7)            1  2  3  4  5
```

Free text:
- Most compelling moment: ________________________________________
- Most broken / fake moment: _____________________________________
- Any character break (quote it): ________________________________
- Grader evidence that was wrong/hallucinated: ___________________

---

## 6. Player debrief (ask before they see any score)

1. Did it feel like talking to a real client? Where did that hold up or break?
2. What did Priya actually need? *(Did they get it? Note whether they say the
   real need or just "a dashboard.")*
3. If they got it — what tipped you off? *(This is your read on whether the
   reveal ladder did its job.)*
4. What did you make of Marcus showing up?
5. Anything feel fake, confusing, or broken?
6. Would you want to practice on something like this? Why / why not?

---

## 7. Turn the session into a calibration fixture

This is how the ≥10 you need for real calibration accumulates.

Run this from the same directory / `SIM_DB_PATH` the app used — one command does
the export, the grade comparison, and the fixture write:

```bash
python -m sim.app.save_fixture <session-id> \
    --id found_need_thin_scope \
    --score discovery=0.75 --score scoping=0.4 \
    --score stakeholders=0.6 --score communication=0.7 \
    --summary "Found the need, scoped too thin, brushed off Marcus." \
    --repo /path/to/testers/repo \
    --grade
```

- `--score` keys must match the scenario rubric (it errors loudly otherwise).
- `--grade` prints the **human-vs-machine** comparison to log in the sheet, and
  stashes the machine result in the fixture under `_machine_reference` (ignored by
  the harness; there for later review). Needs a real `LLM_PROVIDER`.
- `--repo` captures the tester's git history as the build record automatically.
- The fixture lands in `calibration/<scenario>/NN_<id>.json`, auto-numbered, and
  the command tells you how many fixtures you have and how many more to reach 10.
5. Once you have ~10 across the quality range, run
   `LLM_PROVIDER=<real> python -m sim.app.calibrate --consistency` and read the
   report. Only if it PASSES do you set `GRADER_CALIBRATED=true`.

---

## 8. How many players, and what the results decide

**Cadence:** 1 facilitator pilot, then **3–5 fresh players**. Five cold users
surface the large majority of experience/usability problems; that's enough to
decide on the *feel*. It is **not** enough to validate the grader — that keeps
accumulating toward ≥10 across playtests.

**Decision criteria after the first 3–5 fresh players:**

- **Personas / experience — GO** if, across the sessions: believability median
  ≥ 4/5, **H2 (anti-leak) held in every session**, and ≥2 of 3 players either
  found the real need or clearly could have from the reveals that were available.
  → The core bet is validated; the experience lands.

- **Persona / experience — FIX FIRST** if personas break character on a *strong*
  model, or good discovery questions don't reliably unlock (H3 fails), or the
  loop feels flat even when everything works. → This is a design/prompt problem;
  fix it before building the container environment. Building infrastructure under
  a loop that isn't fun is the expensive mistake.

- **Grader — signal, not verdict.** If human-vs-grader deltas are wild (>0.30 on
  most sessions) or evidence is hallucinated (H6 fails), prioritize grader-prompt
  work and re-run calibration before trusting any score. If deltas are tight,
  just keep banking fixtures.

- **Next build decision.** Only after "personas/experience = GO": the
  containerized environment (the one new adapter) becomes the priority, because
  now you know the thing it's scaling is worth scaling.

---

## 9. Facilitator one-pager (print this)

```
BEFORE     [ ] strong model set        [ ] scenario = churn_dashboard
           [ ] app loads, 2 personas   [ ] GRADER_CALIBRATED unset
           [ ] fresh player (not a builder)
           [ ] pilot run done once
BRIEF      [ ] read verbatim, add nothing
DURING     [ ] silent, timestamped notes vs H1–H7   [ ] note session id
           [ ] do NOT reveal: hidden need / ladder / Marcus / coaching
AFTER      [ ] debrief BEFORE showing any score
           [ ] Part A (4 numbers + evidence)   [ ] Part B (6 Likert + free text)
           [ ] export transcript  [ ] run grader  [ ] log human vs grader delta
           [ ] save fixture into calibration/churn_dashboard/
DECIDE     [ ] after 3–5: GO / FIX-FIRST on personas   [ ] grader = signal only
```
