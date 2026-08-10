#!/usr/bin/env bash
# =============================================================================
# Stop the natively-run stack: kills exactly the processes run_native.sh
# started (PIDs recorded under ./run/). An Ollama that was already running
# before run_native.sh (no pid file) is deliberately left alone.
# =============================================================================
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

pid_files=(run/api.pid run/ollama.pid)
found=0
for pid_file in "${pid_files[@]}"; do
  [[ -f "$pid_file" ]] && found=1
done

if [[ "$found" -eq 0 ]]; then
  echo "==> Nothing to stop (no pid files under run/)."
  exit 0
fi

process_running() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null && return 0
  case "${OSTYPE:-}" in
    msys*|cygwin*|win32*)
      command -v tasklist.exe >/dev/null 2>&1 || return 1
      MSYS2_ARG_CONV_EXCL='*' tasklist.exe /FI "PID eq $pid" /NH 2>/dev/null \
        | tr -d '\r' \
        | awk -v expected="$pid" '$2 == expected { found = 1 } END { exit !found }'
      ;;
    *)
      return 1
      ;;
  esac
}

force_stop() {
  local pid="$1"
  case "${OSTYPE:-}" in
    msys*|cygwin*|win32*)
      if command -v taskkill.exe >/dev/null 2>&1; then
        MSYS2_ARG_CONV_EXCL='*' taskkill.exe /PID "$pid" /T /F >/dev/null 2>&1 || true
        return
      fi
      ;;
  esac
  kill -9 "$pid" 2>/dev/null || true
}

for pidfile in "${pid_files[@]}"; do
  [[ -f "$pidfile" ]] || continue
  name="$(basename "$pidfile" .pid)"
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  if process_running "$pid"; then
    echo "==> Stopping $name (pid $pid)"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 10); do
      process_running "$pid" || break
      sleep 1
    done
    process_running "$pid" && force_stop "$pid"
  else
    echo "==> $name PID file is stale"
  fi
  rm -f "$pidfile"
done

echo "==> Done."
