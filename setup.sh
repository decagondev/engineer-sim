#!/usr/bin/env bash
# One-command setup for macOS / Linux. Creates a virtual environment,
# installs dependencies, and runs the preflight check.
set -e
cd "$(dirname "$0")"

echo "Setting up the Engineering Flight Simulator…"
echo

# pick python
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python is not installed. Get it from https://www.python.org/downloads/ and run this again."
  exit 1
fi

"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
echo "Installing dependencies (this can take a minute)…"
pip install -r requirements.txt >/dev/null
echo "Done installing."
echo

python doctor.py || true

echo
echo "────────────────────────────────────────────────────────"
echo "Next time, activate the environment first:"
echo "    source .venv/bin/activate"
echo "Then start it with the command the check suggested above."
echo "────────────────────────────────────────────────────────"
