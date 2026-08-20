#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BACKEND_UVICORN="backend/.venv/bin/uvicorn"
if [[ ! -x "$BACKEND_UVICORN" ]]; then
  echo "Backend virtual environment is missing. Run 'make install' first." >&2
  exit 1
fi

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"$BACKEND_UVICORN" dolosmeta.app:app \
  --app-dir backend \
  --host 127.0.0.1 \
  --port "${BACKEND_PORT:-8000}" \
  --no-server-header &
BACKEND_PID=$!

export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:${BACKEND_PORT:-8000}}"
npm run dev
