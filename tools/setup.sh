#!/usr/bin/env sh
# Create the project-local Python environment (.venv) for tools/collect.
# Usage (repo root):  sh tools/setup.sh
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
venv="$root/.venv"

if [ ! -d "$venv" ]; then
  python3 -m venv "$venv" 2>/dev/null || python -m venv "$venv"
fi
if [ -x "$venv/bin/python" ]; then python="$venv/bin/python"; else python="$venv/Scripts/python.exe"; fi
"$python" -m pip install --quiet --upgrade pip
"$python" -m pip install --quiet -r "$root/tools/requirements.txt"

if [ ! -f "$root/.env" ]; then
  cp "$root/.env.example" "$root/.env"
  echo "Created .env from .env.example. Set EDINET_API_KEY if available."
fi
"$python" -I "$root/tools/collect/preflight.py"
