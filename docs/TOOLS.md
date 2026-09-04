# Coding tools & prerequisites — links

You write code in **your own tool**; the simulator works with any of them. Below
is what each thing is, where to get it, and where its docs live. Links verified
current as of writing — if one has moved, search the tool's name.

## Editors & AI coding agents (pick one to start)

- **VS Code** — the standard code editor; great first choice.
  Download: https://code.visualstudio.com · Docs: https://code.visualstudio.com/docs
- **Cursor** — VS Code with AI built in (chat, edits, agent).
  Site: https://cursor.com · Download: https://cursor.com/download · Docs: https://docs.cursor.com
- **Claude Code** — Anthropic's agent for the terminal / IDE (needs Node.js).
  Install: `npm install -g @anthropic-ai/claude-code`
  Docs: https://docs.claude.com/en/docs/claude-code/overview ·
  Package: https://www.npmjs.com/package/@anthropic-ai/claude-code
- **OpenCode** — open-source terminal coding agent, works with many providers.
  Install: `curl -fsSL https://opencode.ai/install | bash`  (or `npm i -g opencode-ai`)
  Site: https://opencode.ai · Docs: https://opencode.ai/docs
- **Codex CLI** — OpenAI's terminal coding agent.
  Install: `npm install -g @openai/codex`  (or `brew install codex`)
  Repo/docs: https://github.com/openai/codex · https://developers.openai.com/codex/cli

> New to this? Start with **VS Code** or **Cursor** — they have a normal window.
> Terminal agents (Claude Code, OpenCode, Codex) are powerful once you're comfy
> on the command line.

## Version control

- **Git** — track changes and commit your work (your history is reviewed).
  Download: https://git-scm.com/downloads · Docs: https://git-scm.com/doc
- **GitHub** — host repos (used by the fork-and-submit flow). https://github.com ·
  a read-only token (https://github.com/settings/tokens) as `GITHUB_TOKEN` raises the
  server's GitHub API rate limit for a class.

## Running the AI people

- **Ollama** — run models locally, for free. https://ollama.com ·
  Download: https://ollama.com/download ·
  After installing: `ollama pull llama3.1:8b`
- **Anthropic API** — highest persona quality (paid). Get a key:
  https://console.anthropic.com
- **Groq API** — fast, cheap inference for **open models** (Llama, Mixtral, Gemma).
  Get a key: https://console.groq.com/keys · Models: https://console.groq.com/docs/models ·
  Set `GROQ_API_KEY` and start with `LLM_PROVIDER=groq` (no extra package).

## The environment

- **Docker Desktop** — the isolated per-session dev box.
  Download: https://www.docker.com/products/docker-desktop/ · Docs: https://docs.docker.com/desktop/

## Runtimes

- **Python 3.11+** — runs the simulator itself. https://www.python.org/downloads/
- **Node.js** — needed by Claude Code, Codex, and OpenCode (npm installs). https://nodejs.org
