#!/usr/bin/env bash
# =============================================================================
# Stop the natively-run stack: kills exactly the processes run_native.sh
# started (PIDs recorded under ./run/). An Ollama that was already running
# before run_native.sh (no pid file) is deliberately left alone.
# =============================================================================
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

shopt -s nullglob
pids=(run/*.pid)
if [[ ${#pids[@]} -eq 0 ]]; then
  echo "==> Nothing to stop (no pid files under run/)."
  exit 0
fi

for pidfile in "${pids[@]}"; do
  name="$(basename "$pidfile" .pid)"
  pid="$(cat "$pidfile")"
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
  rm -f "$pidfile"
done

echo "==> Done."
