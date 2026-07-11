#!/usr/bin/env bash
# =============================================================================
# Smoke test: is every service in the stack reachable?
# Checks ollama, qdrant, the FastAPI app (/health), and Open WebUI.
# Exits non-zero if any check fails.
# =============================================================================
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Read one variable from .env. Never `source` it: values contain spaces and
# UTF-8 (ASSISTANT_NAME, WEBUI_NAME), which the shell would try to execute.
env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

API_PORT="$(env_get API_PORT)"
API_PORT="${API_PORT:-8000}"
OPEN_WEBUI_PORT="$(env_get OPEN_WEBUI_PORT)"
OPEN_WEBUI_PORT="${OPEN_WEBUI_PORT:-3000}"

fail=0
check() {
  local name="$1" url="$2"
  if curl -fsS -o /dev/null --max-time 5 "$url"; then
    echo "  [ OK ] $name  ($url)"
  else
    echo "  [FAIL] $name  ($url)"
    fail=1
  fi
}

echo "==> Health checks (host-facing ports)"
check "Ollama"      "http://localhost:11434/api/tags"
check "Qdrant"      "http://localhost:6333/healthz"
check "FastAPI app" "http://localhost:${API_PORT}/health"
check "Open WebUI"  "http://localhost:${OPEN_WEBUI_PORT}/"

if [[ "$fail" -eq 0 ]]; then
  echo "==> All services healthy."
else
  echo "==> One or more services are DOWN." >&2
fi
exit "$fail"
