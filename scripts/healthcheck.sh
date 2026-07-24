#!/usr/bin/env bash
# =============================================================================
# Smoke test for the native stack: Ollama, FastAPI (including embedded Qdrant),
# and Open WebUI. Exits non-zero when any required endpoint is unavailable.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

API_PORT="$(env_get API_PORT)";               API_PORT="${API_PORT:-8000}"
OPEN_WEBUI_PORT="$(env_get OPEN_WEBUI_PORT)"; OPEN_WEBUI_PORT="${OPEN_WEBUI_PORT:-3000}"
OLLAMA_BASE_URL="$(env_get OLLAMA_BASE_URL)"; OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

check_endpoint() {
  local name="$1" url="$2" pid_file="$3" pid_info=""
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      pid_info=" (PID: $pid)"
    else
      pid_info=" (stale PID file)"
    fi
  fi
  if curl -fsS -o /dev/null --max-time 5 "$url"; then
    echo "  [ OK ] $name ($url)$pid_info"
  else
    echo "  [FAIL] $name ($url)$pid_info" >&2
    return 1
  fi
}

echo "==> Health checks"
fail=0
check_endpoint "Ollama" "${OLLAMA_BASE_URL}/api/tags" "run/ollama.pid" || fail=1
echo "  [ -- ] Qdrant (embedded in FastAPI; covered by the API health check)"
check_endpoint "FastAPI" "http://localhost:${API_PORT}/health" "run/api.pid" || fail=1
check_endpoint "Open WebUI" "http://localhost:${OPEN_WEBUI_PORT}/" "run/webui.pid" || fail=1
exit "$fail"
