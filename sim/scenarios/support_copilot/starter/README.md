# Support copilot — starter

Dev (Head of Support) wants "an AI chatbot" on the help site. Talk to Dev before
building — a chatbot that confidently gives *wrong* answers about a regulated
product is worse than no chatbot, and there's more to this than a chat box.

## What's in here
- `docs/` — the "knowledge", scattered across sources and inconsistent with each
  other (a Notion export, a help-centre FAQ, a policy PDF-turned-text). They don't
  agree, and nothing links an answer back to a source.
- `src/answer.py` — a naive stub that "answers" a question. It has no grounding,
  no citations, and no way to tell if an answer is right.

## Heads up
There's no way here to measure whether answers are correct before shipping. In a
fintech, "sounds confident but wrong" is a compliance incident. Part of the job is
figuring out what actually needs building given that.

Commit as you go — your git history is part of how the work is reviewed.
