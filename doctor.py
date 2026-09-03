#!/usr/bin/env python3
"""Preflight check for the Engineering Flight Simulator.

Run this before you start:  python doctor.py

It checks what's installed, tells you plainly what's missing, and gives you the
right download link for your operating system. Nothing here changes your
computer — it only looks.
"""
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

OS = platform.system()   # 'Windows', 'Darwin' (mac), 'Linux'
OSNAME = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(OS, OS)

GREEN, YELLOW, RED, DIM, BOLD, END = "\033[92m", "\033[93m", "\033[91m", "\033[2m", "\033[1m", "\033[0m"
if OS == "Windows" and not os.environ.get("WT_SESSION"):
    GREEN = YELLOW = RED = DIM = BOLD = END = ""   # avoid garbled codes in old consoles

OK, WARN, BAD = f"{GREEN}✓{END}", f"{YELLOW}!{END}", f"{RED}✗{END}"

results = {"ok": 0, "warn": 0, "bad": 0}


def line(mark, title, detail="", link=""):
    print(f"  {mark}  {BOLD}{title}{END}")
    if detail:
        print(f"       {detail}")
    if link:
        print(f"       {DIM}→ {link}{END}")


def ok(title, detail=""):
    results["ok"] += 1; line(OK, title, detail)


def warn(title, detail="", link=""):
    results["warn"] += 1; line(WARN, title, detail, link)


def bad(title, detail="", link=""):
    results["bad"] += 1; line(BAD, title, detail, link)


def have(cmd):
    return shutil.which(cmd) is not None


def run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception:
        return False, ""


def http_ok(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200, r.read().decode("utf-8", "ignore")
    except Exception:
        return False, ""


print(f"\n{BOLD}Engineering Flight Simulator — preflight check{END}")
print(f"{DIM}Operating system detected: {OSNAME}{END}\n")

# --- Python (required) ---------------------------------------------------
print(f"{BOLD}Required{END}")
v = sys.version_info
if v >= (3, 11):
    ok(f"Python {v.major}.{v.minor} — good")
else:
    bad(f"Python {v.major}.{v.minor} is too old (need 3.11+)",
        "Install a newer Python, then run this again.",
        "https://www.python.org/downloads/")

if have("pip") or have("pip3") or run([sys.executable, "-m", "pip", "--version"])[0]:
    ok("pip (Python package installer) — found")
else:
    bad("pip not found", "It usually comes with Python. Reinstall Python.",
        "https://www.python.org/downloads/")

# --- Git (recommended) ---------------------------------------------------
print(f"\n{BOLD}Recommended{END}")
if have("git"):
    ok("Git — found", run(["git", "--version"])[1])
else:
    warn("Git not found",
         "You'll want Git to work on the code and to commit your progress.",
         "https://git-scm.com/downloads")

# --- Docker (recommended for the real workspace) -------------------------
if have("docker"):
    running, _ = run(["docker", "info"])
    if running:
        ok("Docker — installed and running",
           "The 'Workspace' app will give you a real, isolated dev box.")
    else:
        warn("Docker is installed but not running",
             f"Start Docker Desktop, then run this again. (On {OSNAME}, look for the "
             "whale icon.)",
             "https://docs.docker.com/desktop/")
else:
    warn("Docker not found (optional)",
         "Without it you can still do everything except the containerised workspace; "
         "you can work in a plain local folder instead.",
         "https://www.docker.com/products/docker-desktop/")

# --- A model provider: how the 'people' are powered ----------------------
print(f"\n{BOLD}How the AI people are powered (pick one){END}")
ollama_up, tags = http_ok("http://localhost:11434/api/tags")
anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
groq_key = bool(os.environ.get("GROQ_API_KEY"))

if have("ollama") or ollama_up:
    if ollama_up:
        import json
        try:
            models = [m["name"] for m in json.loads(tags).get("models", [])]
        except Exception:
            models = []
        if models:
            ok("Ollama — running with a model (free, local)",
               "Models available: " + ", ".join(models[:5]))
        else:
            warn("Ollama is running but no model is pulled",
                 "Pull one first:  ollama pull llama3.1:8b",
                 "https://ollama.com")
    else:
        warn("Ollama is installed but not running",
             "Start it (open the Ollama app or run 'ollama serve'), then "
             "'ollama pull llama3.1:8b'.",
             "https://ollama.com")
else:
    warn("Ollama not found (free option)",
         "Ollama runs the AI people on your own machine for free — good for practice.",
         "https://ollama.com/download")

if anthropic_key:
    ok("Anthropic API key — set (higher-quality people)")
else:
    warn("No Anthropic API key set (paid, higher quality)",
         "Optional. Set ANTHROPIC_API_KEY for the best persona quality.",
         "https://console.anthropic.com")

if groq_key:
    ok("Groq API key — set (fast, cheap open models)")
else:
    warn("No Groq API key set (fast open models like Llama, cheap)",
         "Optional. Set GROQ_API_KEY to run open models fast via Groq.",
         "https://console.groq.com/keys")

# --- Node.js (optional; some coding tools need it) -----------------------
print(f"\n{BOLD}Optional{END}")
if have("node"):
    ok("Node.js — found", "Needed by some coding tools (Claude Code, Codex, OpenCode).")
else:
    warn("Node.js not found (optional)",
         "Only needed if you install a coding tool that requires it.",
         "https://nodejs.org")

# --- Verdict -------------------------------------------------------------
print(f"\n{BOLD}Summary{END}")
print(f"  {OK} {results['ok']} good   {WARN} {results['warn']} to look at   {BAD} {results['bad']} must fix\n")

if results["bad"]:
    print(f"{RED}Fix the ✗ items above before starting.{END} They're required.\n")
    sys.exit(1)

# figure out which provider mode is available
if ollama_up:
    provider = ("ollama", "LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.1:8b")
elif anthropic_key:
    provider = ("anthropic", "LLM_PROVIDER=anthropic ANTHROPIC_MODEL=<current-model>")
elif groq_key:
    provider = ("groq", "LLM_PROVIDER=groq GROQ_MODEL=llama-3.3-70b-versatile")
else:
    provider = ("fake", "LLM_PROVIDER=fake  (canned replies — set up Ollama for real practice)")

env = "docker" if (have("docker") and run(["docker", "info"])[0]) else "local_folder"
print(f"{GREEN}You're ready to run.{END}  Suggested start:\n")
if OS == "Windows":
    print(f"   set {provider[1].replace(' ', '&& set ')}&& set ENV_PROVIDER={env}&& python -m uvicorn sim.app.main:app")
else:
    print(f"   {provider[1]} ENV_PROVIDER={env} python -m uvicorn sim.app.main:app")
print(f"\nThen open {BOLD}http://127.0.0.1:8000{END} in your browser.")
print(f"(Instructors: {BOLD}http://127.0.0.1:8000/instructor{END})\n")
