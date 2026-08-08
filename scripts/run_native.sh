#!/usr/bin/env bash
# =============================================================================
# Start the whole stack NATIVELY (no Docker) on macOS / Linux:
#   - Ollama       (started only if not already running, e.g. the menu-bar app)
#   - FastAPI app  (uvicorn from .venv; Qdrant runs EMBEDDED in this process;
#                   also serves the landing/admin/chat frontend on the same port)
# Idempotent: services already listening on their port are left alone.
# Logs -> ./logs/*.log ; PIDs of processes started here -> ./run/*.pid
# (scripts/stop_native.sh stops exactly those). Fully offline after setup.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Read one variable from .env. Never `source` it: values contain spaces and
# UTF-8 (ASSISTANT_NAME), which the shell would try to execute.
env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

API_HOST="$(env_get API_HOST)";               API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="$(env_get API_PORT)";               API_PORT="${API_PORT:-8000}"
OLLAMA_BASE_URL="$(env_get OLLAMA_BASE_URL)"; OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
API_PUBLIC_BASE_URL="$(env_get API_PUBLIC_BASE_URL)"
API_PUBLIC_BASE_URL="${API_PUBLIC_BASE_URL:-http://localhost:${API_PORT}}"

# FE1 (2026-08-05 audit) partial fix: citation links silently only open on
# THIS machine for any employee elsewhere on the LAN when API_HOST is opened
# up but API_PUBLIC_BASE_URL is left at its loopback default. Detect the
# LAN IP and print an actionable suggestion -- never auto-edit .env, since
# opening the LAN also needs API_SHARED_SECRET set (see SEC1, README).
if [[ "$API_HOST" == "0.0.0.0" \
   && ( "$API_PUBLIC_BASE_URL" == http://localhost* || "$API_PUBLIC_BASE_URL" == http://127.0.0.1* ) ]]; then
  lan_ip=""
  if command -v ipconfig >/dev/null 2>&1; then
    lan_ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  fi
  if [[ -z "$lan_ip" ]] && command -v hostname >/dev/null 2>&1; then
    lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  if [[ -n "$lan_ip" ]]; then
    echo "==> NOTE: API_HOST=0.0.0.0 (LAN-reachable) but API_PUBLIC_BASE_URL is still" >&2
    echo "    loopback (${API_PUBLIC_BASE_URL}) -- citation links in answers will only" >&2
    echo "    open on THIS machine for employees elsewhere on the LAN. Suggested fix:" >&2
    echo "    set API_PUBLIC_BASE_URL=http://${lan_ip}:${API_PORT} in .env, and set" >&2
    echo "    API_SHARED_SECRET (see .env.example) before doing so -- see README" >&2
    echo "    (\"Liên kết trích dẫn cho người dùng trong mạng LAN\")." >&2
  fi
fi

if [[ ! -d .venv ]]; then
  echo "ERROR: .venv not found — run 'bash scripts/setup_native.sh' first." >&2
  exit 1
fi

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

echo "==> Stack starting. First API start loads models and can take ~1 minute."
echo "    Chat:         http://localhost:${API_PORT}/chat"
echo "    Admin:        http://localhost:${API_PORT}/admin"
echo "    Landing:      http://localhost:${API_PORT}/"
echo "    Health:       bash scripts/healthcheck.sh"
echo "    Stop:         bash scripts/stop_native.sh"
