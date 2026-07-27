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
listening() { curl -sS -o /dev/null --max-time 2 "$1" 2>/dev/null; }
log_start() { printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$2" >> "$1"; }

if listening "${OLLAMA_BASE_URL}/api/tags"; then
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
  for _ in $(seq 1 30); do
    listening "${OLLAMA_BASE_URL}/api/tags" && break
    sleep 1
  done
  if ! listening "${OLLAMA_BASE_URL}/api/tags"; then
    echo "ERROR: Ollama did not become ready; see logs/ollama.log." >&2
    exit 1
  fi
fi

if listening "http://localhost:${API_PORT}/health"; then
  echo "==> API already running on port ${API_PORT}"
else
  echo "==> Starting FastAPI on port ${API_PORT} (logs/api.log)"
  log_start logs/api.log "Starting FastAPI on port ${API_PORT}"
  HF_HOME="$ROOT_DIR/models/hf" PYTHONUNBUFFERED=1 \
    nohup "$APP_UVICORN" app.main:app --host "$API_HOST" --port "$API_PORT" \
    >> logs/api.log 2>&1 &
  echo $! > run/api.pid
fi

if listening "http://localhost:${OPEN_WEBUI_PORT}/"; then
  echo "==> Open WebUI already running on port ${OPEN_WEBUI_PORT}"
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

echo "==> Stack starting. First API start may take about one minute."
echo "    Chat UI:    http://localhost:${OPEN_WEBUI_PORT}"
echo "    Admin page: http://localhost:${API_PORT}"
echo "    Health:     bash scripts/healthcheck.sh"
echo "    Stop:       bash scripts/stop_native.sh"
