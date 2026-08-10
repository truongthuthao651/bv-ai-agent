#!/usr/bin/env bash
# =============================================================================
# Start Ollama, FastAPI (with embedded Qdrant), and Open WebUI natively.
# Existing services are left alone. Logs live in ./logs and PID files for
# processes started here live in ./run.
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

API_HOST="$(env_get API_HOST)";                     API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="$(env_get API_PORT)";                     API_PORT="${API_PORT:-8000}"
OPEN_WEBUI_PORT="$(env_get OPEN_WEBUI_PORT)";       OPEN_WEBUI_PORT="${OPEN_WEBUI_PORT:-3000}"
OLLAMA_BASE_URL="$(env_get OLLAMA_BASE_URL)";       OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
QDRANT_LOCAL_PATH="$(env_get QDRANT_LOCAL_PATH)";   QDRANT_LOCAL_PATH="${QDRANT_LOCAL_PATH:-./qdrant_storage/local}"
OPENAI_API_BASE_URL="$(env_get OPENAI_API_BASE_URL)"; OPENAI_API_BASE_URL="${OPENAI_API_BASE_URL:-http://localhost:${API_PORT}/v1}"
OPENAI_API_KEY="$(env_get OPENAI_API_KEY)";         OPENAI_API_KEY="${OPENAI_API_KEY:-local-no-auth}"
WEBUI_AUTH="$(env_get WEBUI_AUTH)";                 WEBUI_AUTH="${WEBUI_AUTH:-false}"
WEBUI_NAME="$(env_get WEBUI_NAME)";                 WEBUI_NAME="${WEBUI_NAME:-Local RAG Assistant}"
DEFAULT_MODELS="$(env_get DEFAULT_MODELS)";         DEFAULT_MODELS="${DEFAULT_MODELS:-bao-viet-life}"

APP_PYTHON="$(venv_executable .venv python python || true)"
APP_UVICORN="$(venv_executable .venv uvicorn uvicorn || true)"
WEBUI_PYTHON="$(venv_executable .venv-webui python python || true)"
WEBUI_COMMAND="$(venv_executable .venv-webui open-webui open-webui || true)"
if [[ -z "$APP_PYTHON" || -z "$APP_UVICORN" || -z "$WEBUI_PYTHON" || -z "$WEBUI_COMMAND" ]]; then
  echo "ERROR: required executables are missing. Run bash scripts/setup_native.sh first." >&2
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
    *)
      return 1
      ;;
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
  local name="$1" url="$2" attempts="$3" delay="$4"
  local attempt
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    healthy "$url" && return 0
    sleep "$delay"
  done
  echo "ERROR: ${name} did not become healthy at ${url}." >&2
  return 1
}

for service in ollama api webui; do
  remove_stale_pid_file "$service" "run/${service}.pid"
done

startup_failed=0

if healthy "${OLLAMA_BASE_URL}/api/tags"; then
  echo "==> Ollama already running at ${OLLAMA_BASE_URL}"
else
  if pid_file_running run/ollama.pid; then
    echo "==> Ollama PID $(cat run/ollama.pid) is still running; waiting for readiness"
  else
    if ! command -v ollama >/dev/null 2>&1; then
      echo "ERROR: Ollama is not running and its CLI is not on PATH." >&2
      exit 1
    fi
    echo "==> Starting Ollama (logs/ollama.log)"
    log_start logs/ollama.log "Starting Ollama"
    nohup ollama serve >> logs/ollama.log 2>&1 &
    echo $! > run/ollama.pid
  fi
  if ! wait_for_health "Ollama" "${OLLAMA_BASE_URL}/api/tags" 30 1; then
    echo "       See logs/ollama.log." >&2
    exit 1
  fi
fi

API_HEALTH_URL="http://localhost:${API_PORT}/health"
if reachable "$API_HEALTH_URL"; then
  if healthy "$API_HEALTH_URL"; then
    echo "==> API already healthy on port ${API_PORT}"
  else
    echo "ERROR: API is reachable on port ${API_PORT} but reports unhealthy." >&2
    echo "       Not starting a duplicate process; run the healthcheck and inspect logs/api.log." >&2
    startup_failed=1
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
  if ! wait_for_health "FastAPI/embedded Qdrant" "$API_HEALTH_URL" 120 1; then
    echo "       See logs/api.log." >&2
    startup_failed=1
  fi
fi

WEBUI_URL="http://localhost:${OPEN_WEBUI_PORT}/"
if healthy "$WEBUI_URL"; then
  echo "==> Open WebUI already healthy on port ${OPEN_WEBUI_PORT}"
else
  if reachable "$WEBUI_URL"; then
    echo "ERROR: Open WebUI is reachable on port ${OPEN_WEBUI_PORT} but reports unhealthy." >&2
    echo "       Not starting a duplicate process; inspect logs/webui.log." >&2
    startup_failed=1
  else
    if pid_file_running run/webui.pid; then
      echo "==> Open WebUI PID $(cat run/webui.pid) is still running; waiting for readiness"
    else
      echo "==> Starting Open WebUI on port ${OPEN_WEBUI_PORT} (logs/webui.log)"
      log_start logs/webui.log "Starting Open WebUI on port ${OPEN_WEBUI_PORT}"
      "$WEBUI_PYTHON" scripts/open_webui/apply_branding.py >> logs/webui.log 2>&1 || true
      DATA_DIR="$ROOT_DIR/open_webui_data" \
        OPENAI_API_BASE_URL="$OPENAI_API_BASE_URL" \
        OPENAI_API_KEY="$OPENAI_API_KEY" \
        WEBUI_AUTH="$WEBUI_AUTH" \
        WEBUI_NAME="$WEBUI_NAME" \
        DEFAULT_MODELS="$DEFAULT_MODELS" \
        nohup "$WEBUI_COMMAND" serve --host 0.0.0.0 --port "$OPEN_WEBUI_PORT" \
        >> logs/webui.log 2>&1 &
      echo $! > run/webui.pid
    fi
    if ! wait_for_health "Open WebUI" "$WEBUI_URL" 120 1; then
      echo "       See logs/webui.log." >&2
      startup_failed=1
    fi
  fi
fi

if [[ "$startup_failed" -ne 0 ]]; then
  echo "ERROR: one or more native services are unhealthy." >&2
  exit 1
fi

echo "==> Native stack is healthy."
echo "    Chat UI:    http://localhost:${OPEN_WEBUI_PORT}"
echo "    Admin page: http://localhost:${API_PORT}"
echo "    Health:     bash scripts/healthcheck.sh"
echo "    Stop:       bash scripts/stop_native.sh"
