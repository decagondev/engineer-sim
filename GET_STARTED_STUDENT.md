# Getting started — for learners

Welcome. This is a **flight simulator for software engineers**. You'll talk to
an AI client and stakeholders, figure out what actually needs building, do the
work in a real dev environment, and get feedback on how you did it — like a real
job, but safe to get wrong.

This guide assumes **nothing**. Follow it top to bottom. It takes about 15–20
minutes the first time.

---

## 1. What you need

You need one required thing (Python) and a couple of recommended ones. The setup
step below checks all of this for you and gives you links — you don't have to
figure it out yourself.

| Thing | Needed? | What it's for |
|---|---|---|
| **Python 3.11+** | Required | Runs the simulator |
| **A coding tool** | Required | How you actually write code — pick one in §6 |
| **Docker Desktop** | Recommended | Gives you a real, isolated "dev box" for the work |
| **Ollama** *or* an Anthropic API key | Recommended | Powers the AI people (free with Ollama) |
| **Git** | Recommended | Track your work; it's how your progress is reviewed |

Don't install these one by one yet — do step 2 first.

---

## 2. Get the simulator onto your computer

Either download the ZIP your instructor gave you and unzip it, **or**, if you
know Git:

```
git clone <the repo url your instructor gave you>
cd sim-mvp
```

Open a terminal **in that folder** (the one containing `setup.sh` and `doctor.py`).

- **Windows:** open the folder in File Explorer, type `powershell` in the address bar, press Enter.
- **macOS:** right-click the folder → *New Terminal at Folder*.
- **Linux:** right-click → *Open in Terminal*.

---

## 3. Run the setup

This creates an isolated environment, installs everything, and checks your
computer — all in one go.

- **macOS / Linux:**
  ```
  ./setup.sh
  ```
- **Windows (PowerShell):**
  ```
  powershell -ExecutionPolicy Bypass -File setup.ps1
  ```

At the end it prints a **preflight check** with green ✓ / yellow ! / red ✗. Fix
any **red** items (there usually aren't any). Yellow items are optional and each
comes with a link.

You can re-run the check any time:
```
python doctor.py
```

---

## 4. Get Docker (recommended)

Docker gives you a clean, throwaway "dev box" per session — the realistic way to
work. Install **Docker Desktop**, then **start it** (you'll see a whale icon):

- Download: https://www.docker.com/products/docker-desktop/
- Docs: https://docs.docker.com/desktop/

> No Docker? You can still do everything — the simulator falls back to a plain
> local folder for your workspace. Docker just makes it cleaner and more real.

---

## 5. Power the AI people (pick one)

The client and stakeholders are AI. You choose what runs them:

- **Free, on your machine — Ollama (recommended for practice).**
  Install from https://ollama.com/download, then in a terminal:
  ```
  ollama pull llama3.1:8b
  ```
  First replies can take 10–40 seconds on a laptop — that's normal.

- **Best quality — Anthropic API key (paid).** Get a key at
  https://console.anthropic.com and set `ANTHROPIC_API_KEY`.

- **Fast & cheap open models — Groq (paid, inexpensive).** Runs Llama and other
  open models very fast. `pip install groq`, get a key at
  https://console.groq.com/keys, set `GROQ_API_KEY`, and start with
  `LLM_PROVIDER=groq`.

- **Just looking around — "fake" mode (no setup).** The people reply with one
  canned line. Fine to see the interface; useless for real practice.

---

## 6. Choose a coding tool

You write the actual code in **your own tool** — the simulator doesn't lock you
in. Any of these work. See **[docs/TOOLS.md](docs/TOOLS.md)** for full links and
setup; the short list:

- **VS Code** — the classic editor. https://code.visualstudio.com
- **Cursor** — VS Code + built-in AI. https://cursor.com
- **Claude Code** — Anthropic's terminal agent. https://docs.claude.com/en/docs/claude-code/overview
- **OpenCode** — open-source terminal agent. https://opencode.ai
- **Codex CLI** — OpenAI's terminal agent. https://github.com/openai/codex

If you're brand new: start with **VS Code** or **Cursor** (they have a normal
window and buttons). Terminal agents are great once you're comfortable.

---

## 7. Start it and open your browser

Use the exact command the preflight check suggested (it's tailored to what you
have). It looks like one of these:

- **macOS / Linux:**
  ```
  source .venv/bin/activate
  LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.1:8b ENV_PROVIDER=docker python -m uvicorn sim.app.main:app
  ```
- **Windows (PowerShell):**
  ```
  .\.venv\Scripts\Activate.ps1
  $env:LLM_PROVIDER="ollama"; $env:OLLAMA_MODEL="llama3.1:8b"; $env:ENV_PROVIDER="docker"; python -m uvicorn sim.app.main:app
  ```

Then open **http://127.0.0.1:8000** in your browser. If your instructor gave you
a session link (like `http://127.0.0.1:8000/#s-abc123`), open that instead — it
loads your assigned scenario.

To stop the server: press **Ctrl+C** in the terminal.

---

## 7b. If your instructor gave you a server link

If you're in a class, you may not run the server yourself at all — your
instructor runs it and gives you a link like `http://192.168.1.20:8000/#s-abc123`.
Just open that link. You still do steps 5–6 (a coding tool) on your own
machine, and you hand your work back with the **Submit** app (see §8). Full
details: **[docs/CLASSROOM.md](docs/CLASSROOM.md)**.

## 8. Your first session

1. You land on a **desktop** with a dock of apps.
2. Open **Team Chat**. Say hello to the client. **Don't** just build what they
   ask for — ask questions and figure out what they *actually* need. (That's the
   whole point. The client starts vague on purpose.)
3. Watch the dock: stakeholders may **message**, **email**, or **file tickets**
   as you go. Handle them.
4. Open **Workspace** to create your dev box. It shows you where your files are
   (and, with Docker, a `docker exec` command to get a terminal inside it).
5. Open that folder / container in your coding tool, read the starter code, and
   **build**. **Commit as you go** — your Git history is part of how the work is
   reviewed.
6. Use **Tickets** to scope the work, **Files** to browse the project, and
   **Mail** for the more formal stakeholder threads.
7. If you're on your own machine (or a classroom server), use the **Submit**
   app: download the starter code, build locally, then submit a git patch of
   your changes.
8. When you're done, hit **Grade run** in Team Chat for feedback.

There's no single right answer — work it like a real client.

---

## Troubleshooting

- **`python` not found (Windows):** try `py` instead of `python`.
- **Port already in use:** add `--port 8001` to the start command and open `:8001`.
- **Docker error in the Workspace app:** make sure Docker Desktop is *running*
  (whale icon), and on Windows that file sharing is enabled for your drive.
- **First AI reply is very slow (Ollama):** normal on a laptop, especially the
  first message while the model loads. Give it a minute.
- **The people only say one canned line:** you're in `fake` mode — set up Ollama
  (§5) for real conversations.
- **Anything else:** re-run `python doctor.py` — it usually tells you what's off.
