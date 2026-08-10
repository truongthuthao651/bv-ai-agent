#!/usr/bin/env bash
# =============================================================================
# Local CI-equivalent: ruff + pytest before committing (or use pre-commit hook).
# =============================================================================
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

venv_executable() {
  local unix_name="$1" windows_name="$2"
  if [[ -x ".venv/bin/$unix_name" ]]; then
    printf '%s\n' ".venv/bin/$unix_name"
  elif [[ -f ".venv/Scripts/$windows_name.exe" ]]; then
    printf '%s\n' ".venv/Scripts/$windows_name.exe"
  else
    return 1
  fi
}

RUFF="$(venv_executable ruff ruff || true)"
PYTEST="$(venv_executable pytest pytest || true)"
if [[ -z "$RUFF" || -z "$PYTEST" ]]; then
  echo "ERROR: .venv not found — run 'bash scripts/setup_native.sh' first." >&2
  exit 1
fi

fail=0

step() {
  local name="$1"
  shift
  echo "==> $name"
  if "$@"; then
    echo "  [ OK ] $name"
  else
    echo "  [FAIL] $name"
    fail=1
  fi
}

step "ruff check"          "$RUFF" check app/ tests/ eval/ scripts/
step "ruff format --check" "$RUFF" format --check app/ tests/ eval/ scripts/
step "pytest"              "$PYTEST" tests/ -x -q

if [[ "$fail" -eq 0 ]]; then
  echo "==> All checks passed."
else
  echo "==> One or more checks FAILED." >&2
fi
exit "$fail"
