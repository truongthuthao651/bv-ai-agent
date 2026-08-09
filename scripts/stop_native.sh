#!/usr/bin/env bash
# =============================================================================
# Stop the natively-run stack: kills processes run_native.sh started (PIDs under
# ./run/), then clears any orphaned uvicorn listener on API_PORT (common when
# the pid file was lost but the old process kept running). Ollama started outside
# run_native.sh is deliberately left alone.
# =============================================================================
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }
API_PORT="$(env_get API_PORT)"; API_PORT="${API_PORT:-8000}"

stop_pid() {
  local name="$1" pid="$2"
  if kill -0 "$pid" 2>/dev/null; then
    echo "==> Stopping $name (pid $pid)"
    kill "$pid"
    for _ in $(seq 1 10); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
  else
    echo "==> $name (pid $pid) already stopped"
  fi
}

shopt -s nullglob
pids=(run/*.pid)
if [[ ${#pids[@]} -eq 0 ]]; then
  echo "==> No pid files under run/."
else
  for pidfile in "${pids[@]}"; do
    name="$(basename "$pidfile" .pid)"
    stop_pid "$name" "$(cat "$pidfile")"
    rm -f "$pidfile"
  done
fi

# Orphan cleanup: old API still on the port after a lost pid file serves stale
# code (e.g. login.html cached at import time before our template reload fix).
if command -v lsof >/dev/null 2>&1; then
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$cmd" == *"uvicorn app.main:app"* ]]; then
      echo "==> Stopping orphaned API on port ${API_PORT} (pid $pid)"
      stop_pid "api-orphan" "$pid"
    fi
  done < <(lsof -ti :"${API_PORT}" 2>/dev/null || true)
fi

echo "==> Done."
