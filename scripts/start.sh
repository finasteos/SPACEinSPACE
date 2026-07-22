#!/usr/bin/env bash
# Start SPACEinSPACE locally (macOS / Linux).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt psycopg2-binary
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example and fill values (or run: supabase start && supabase status -o env)"
  exit 1
fi

# Best-effort: ensure local deps are up
if command -v ollama >/dev/null 2>&1; then
  if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Starting Ollama…"
    brew services start ollama 2>/dev/null || ollama serve &
    sleep 2
  fi
fi

if command -v supabase >/dev/null 2>&1; then
  if ! curl -sf http://127.0.0.1:54321/rest/v1/ >/dev/null 2>&1; then
    echo "Starting local Supabase…"
    supabase start
  fi
fi

echo "Launching conductor (Ctrl+C to quit)…"
exec python main.py
