# Running on a classroom / lab server (Version A)

This is the "semi-local" setup: **one server** on your network runs the chat,
mail, tickets, scenarios and grading. Learners connect to it from their own
laptops, do the actual **coding on their own machines** with their own tools, and
**submit a patch** back for grading. The instructor runs one dashboard and watches
every session from one place.

It's the sweet spot for a classroom — no per-laptop server, no cloud, no accounts.

## On the server (the teacher's machine or a lab box)

1. Set it up once (see `GET_STARTED_STUDENT.md` §2–§5): `./setup.sh`, install
   Docker if you want, pick a model.
2. **Pick a private instructor password** and a real model, then start it:
   ```
   INSTRUCTOR_PASSWORD=choose-something   LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.1:8b  python serve.py
   ```
   (Windows PowerShell: set each with `$env:NAME="value";` then `python serve.py`.)
3. `serve.py` prints the URLs learners should use, e.g. `http://192.168.1.20:8000`,
   and the instructor URL `…/instructor`.

## As the instructor

1. Open `http://<server-ip>:8000/instructor`, log in, onboard.
2. **New session** → pick a scenario + level → **copy the trainee link**. It will
   look like `http://<server-ip>:8000/#s-abc123`.
3. Send each learner their link (chat, email, a shared doc).

## As a learner

1. Open the link the instructor gave you — it loads your assigned scenario.
2. Use **Team Chat** to talk to the client and work out what's really needed.
3. Open the **Submit** app: **Download starter code**, unzip it, `git init`, and
   build in your own editor. Commit as you go.
4. Make a patch (`git format-patch --stdout HEAD~999..HEAD > work.patch` or
   `git diff > work.patch`), paste or upload it in **Submit**, and submit.
5. Hit **Grade run** in Team Chat for feedback.

## How submission works (and why it's a patch)

In this mode the server never sees or runs your code — you keep it on your
machine. You hand back a **git patch** (a text file describing your changes),
which the server stores as your build record and feeds to the grader. The
instructor can read your patch in the replay view. Nothing you run touches the
server, which is exactly why this setup is safe to run for a whole class.

> The server-side **Workspace** app (Docker/local folder) is meant for the
> single-machine setup, where the code lives on the same box as the server. In the
> classroom setup, use **Submit** instead — that's the path built for "code on the
> learner's laptop."

## Sizing & safety (read before a real class)

- **Model load is now the server's, not each laptop's.** Every persona/grader
  call runs on the server. A single Ollama without a GPU will crawl under ~30
  concurrent learners — use a GPU box, or a hosted API — **Anthropic** (best quality) or **Groq**
  (`LLM_PROVIDER=groq`, fast/cheap open models) — with rate limits.
- **The instructor password is a light gate, in cleartext over your LAN.** Set a
  private `INSTRUCTOR_PASSWORD` and only open `/instructor` on the teacher's
  machine. Learner session links are random and unguessable, but shareable — fine
  for a trusted classroom, not for an untrusted network.
- **Firewall:** allow inbound TCP on the port (default 8000) on the server.
- Find the server IP the launcher didn't guess: `ipconfig` (Windows) /
  `ip addr` or `ifconfig` (macOS/Linux).
