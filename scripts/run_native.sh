#!/usr/bin/env bash
# =============================================================================
# Start the whole stack NATIVELY (no Docker) on macOS / Linux:
#   - Ollama       (started only if not already running, e.g. the menu-bar app)
#   - FastAPI app  (uvicorn from .venv; Qdrant runs EMBEDDED in this process)
#   - Open WebUI   (from .venv-webui)
# Idempotent: services already listening on their port are left alone.
# Logs -> ./logs/*.log ; PIDs of processes started here -> ./run/*.pid
# (scripts/stop_native.sh stops exactly those). Fully offline after setup.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Read one variable from .env. Never `source` it: values contain spaces and
# UTF-8 (ASSISTANT_NAME, WEBUI_NAME), which the shell would try to execute.
env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

API_HOST="$(env_get API_HOST)";               API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="$(env_get API_PORT)";               API_PORT="${API_PORT:-8000}"
OPEN_WEBUI_PORT="$(env_get OPEN_WEBUI_PORT)"; OPEN_WEBUI_PORT="${OPEN_WEBUI_PORT:-3000}"
OLLAMA_BASE_URL="$(env_get OLLAMA_BASE_URL)"; OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
OPENAI_API_BASE_URL="$(env_get OPENAI_API_BASE_URL)"
OPENAI_API_BASE_URL="${OPENAI_API_BASE_URL:-http://localhost:${API_PORT}/v1}"
OPENAI_API_KEY="$(env_get OPENAI_API_KEY)";   OPENAI_API_KEY="${OPENAI_API_KEY:-local-no-auth}"
WEBUI_AUTH="$(env_get WEBUI_AUTH)";           WEBUI_AUTH="${WEBUI_AUTH:-false}"
WEBUI_NAME="$(env_get WEBUI_NAME)";           WEBUI_NAME="${WEBUI_NAME:-Trợ lý AI Bảo Việt Life}"
DEFAULT_MODELS="$(env_get DEFAULT_MODELS)";   DEFAULT_MODELS="${DEFAULT_MODELS:-bao-viet-life}"

for venv in .venv .venv-webui; do
  if [[ ! -d "$venv" ]]; then
    echo "ERROR: $venv not found — run 'bash scripts/setup_native.sh' first." >&2
    exit 1
  fi
done

mkdir -p logs run

# TCP reachability (any HTTP status counts as "up"; -f would fail on a 503).
listening() { curl -sS -o /dev/null --max-time 2 "$1" 2>/dev/null; }

# ---- Ollama ----
if listening "${OLLAMA_BASE_URL}/api/tags"; then
  echo "==> Ollama already running at ${OLLAMA_BASE_URL}"
else
  if ! command -v ollama >/dev/null 2>&1; then
    echo "ERROR: Ollama is not running and the CLI is not installed." >&2
    echo "       Install it from https://ollama.com and re-run." >&2
    exit 1
  fi
  echo "==> Starting ollama serve (logs/ollama.log)"
  nohup ollama serve > logs/ollama.log 2>&1 &
  echo $! > run/ollama.pid
  for _ in $(seq 1 30); do
    listening "${OLLAMA_BASE_URL}/api/tags" && break
    sleep 1
  done
fi

# ---- FastAPI app (embedded Qdrant lives inside this process) ----
if listening "http://localhost:${API_PORT}/health"; then
  echo "==> API already running on port ${API_PORT}"
else
  echo "==> Starting FastAPI app on port ${API_PORT} (logs/api.log)"
  # HF_HOME keeps any runtime HF-hub lookups inside ./models (offline cache).
  HF_HOME="$ROOT_DIR/models/hf" PYTHONUNBUFFERED=1 \
    nohup .venv/bin/uvicorn app.main:app --host "$API_HOST" --port "$API_PORT" \
    > logs/api.log 2>&1 &
  echo $! > run/api.pid
fi

# ---- Open WebUI ----
if listening "http://localhost:${OPEN_WEBUI_PORT}/"; then
  echo "==> Open WebUI already running on port ${OPEN_WEBUI_PORT}"
else
  echo "==> Starting Open WebUI on port ${OPEN_WEBUI_PORT} (logs/webui.log)"
  # DATA_DIR here is Open WebUI's OWN storage (chats, settings) — deliberately
  # separate from the app's DATA_DIR in .env, which must not leak into it.
  DATA_DIR="$ROOT_DIR/open_webui_data" \
    OPENAI_API_BASE_URL="$OPENAI_API_BASE_URL" \
    OPENAI_API_KEY="$OPENAI_API_KEY" \
    WEBUI_AUTH="$WEBUI_AUTH" \
    WEBUI_NAME="$WEBUI_NAME" \
    DEFAULT_MODELS="$DEFAULT_MODELS" \
    nohup .venv-webui/bin/open-webui serve --host 0.0.0.0 --port "$OPEN_WEBUI_PORT" \
    > logs/webui.log 2>&1 &
  echo $! > run/webui.pid
fi

echo "==> Stack starting. First API start loads models and can take ~1 minute."
echo "    Chat UI:      http://localhost:${OPEN_WEBUI_PORT}"
echo "    Admin page:   http://localhost:${API_PORT}"
echo "    Health:       bash scripts/healthcheck.sh"
echo "    Stop:         bash scripts/stop_native.sh"
