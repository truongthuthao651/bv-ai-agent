#!/usr/bin/env bash
# =============================================================================
# Start the native stack: Ollama plus FastAPI with embedded Qdrant. FastAPI
# serves the committed landing, chat, and admin frontend from app/static/dist/.
# Works in Windows Git Bash and macOS/Linux without Docker or activation.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

venv_executable() {
  local venv_dir="$1" unix_name="$2" windows_name="$3"
  if [[ -x "$venv_dir/bin/$unix_name" ]]; then
    printf '%s\n' "$venv_dir/bin/$unix_name"
  elif [[ -f "$venv_dir/Scripts/$windows_name.exe" ]]; then
    printf '%s\n' "$venv_dir/Scripts/$windows_name.exe"
  else
    return 1
  fi
}

API_HOST="$(env_get API_HOST)";                   API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="$(env_get API_PORT)";                   API_PORT="${API_PORT:-8000}"
OLLAMA_BASE_URL="$(env_get OLLAMA_BASE_URL)";     OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
QDRANT_LOCAL_PATH="$(env_get QDRANT_LOCAL_PATH)"; QDRANT_LOCAL_PATH="${QDRANT_LOCAL_PATH:-./qdrant_storage/local}"

APP_UVICORN="$(venv_executable .venv uvicorn uvicorn || true)"
if [[ -z "$APP_UVICORN" ]]; then
  echo "ERROR: .venv Uvicorn executable is missing. Run bash scripts/setup_native.sh first." >&2
  exit 1
fi

mkdir -p logs run
reachable() { curl -sS -o /dev/null --max-time 2 "$1" 2>/dev/null; }
healthy() { curl -fsS -o /dev/null --max-time 5 "$1" 2>/dev/null; }
log_start() { printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$2" >> "$1"; }

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
    *) return 1 ;;
  esac
}

pid_file_running() {
  local pid_file="$1" pid
  [[ -f "$pid_file" ]] || return 1
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  process_running "$pid"
}

remove_stale_pid_file() {
  local name="$1" pid_file="$2"
  if [[ -f "$pid_file" ]] && ! pid_file_running "$pid_file"; then
    echo "==> Removing stale ${name} PID file: ${pid_file}"
    rm -f "$pid_file"
  fi
}

wait_for_health() {
  local name="$1" url="$2" attempts="$3" delay="$4" attempt
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    healthy "$url" && return 0
    sleep "$delay"
  done
  echo "ERROR: ${name} did not become healthy at ${url}." >&2
  return 1
}

for service in ollama api; do
  remove_stale_pid_file "$service" "run/${service}.pid"
done

if healthy "${OLLAMA_BASE_URL}/api/tags"; then
  echo "==> Ollama already running at ${OLLAMA_BASE_URL}"
else
  if ! command -v ollama >/dev/null 2>&1; then
    echo "ERROR: Ollama is not running and its CLI is not on PATH." >&2
    exit 1
  fi
  echo "==> Starting Ollama (logs/ollama.log)"
  log_start logs/ollama.log "Starting Ollama"
  nohup ollama serve >> logs/ollama.log 2>&1 &
  echo $! > run/ollama.pid
  wait_for_health "Ollama" "${OLLAMA_BASE_URL}/api/tags" 30 1
fi

API_HEALTH_URL="http://localhost:${API_PORT}/health"
if reachable "$API_HEALTH_URL"; then
  if healthy "$API_HEALTH_URL"; then
    echo "==> API already healthy on port ${API_PORT}"
  else
    echo "ERROR: API is reachable on port ${API_PORT} but reports unhealthy." >&2
    echo "       Not starting a duplicate process; inspect logs/api.log." >&2
    exit 1
  fi
else
  if pid_file_running run/api.pid; then
    echo "==> API PID $(cat run/api.pid) is still running; waiting for readiness"
  else
    echo "==> Starting FastAPI on port ${API_PORT} (logs/api.log)"
    log_start logs/api.log "Starting FastAPI on port ${API_PORT}"
    HF_HOME="$ROOT_DIR/models/hf" PYTHONUNBUFFERED=1 \
      QDRANT_LOCAL_PATH="$QDRANT_LOCAL_PATH" \
      nohup "$APP_UVICORN" app.main:app --host "$API_HOST" --port "$API_PORT" \
      >> logs/api.log 2>&1 &
    echo $! > run/api.pid
  fi
  wait_for_health "FastAPI/embedded Qdrant" "$API_HEALTH_URL" 120 1
fi

echo "==> Native stack is healthy."
echo "    Chat UI:    http://localhost:${API_PORT}/chat"
echo "    Admin page: http://localhost:${API_PORT}/admin"
echo "    Landing:    http://localhost:${API_PORT}/"
echo "    Health:     bash scripts/healthcheck.sh"
echo "    Stop:       bash scripts/stop_native.sh"
