#!/usr/bin/env bash
# =============================================================================
# Local CI-equivalent: ruff + pytest before committing (or use pre-commit hook).
# =============================================================================
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/ruff ]]; then
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

step "ruff check"        .venv/bin/ruff check app/ tests/ eval/ scripts/
step "ruff format --check" .venv/bin/ruff format --check app/ tests/ eval/ scripts/
step "pytest"            .venv/bin/pytest tests/ -x -q

if [[ "$fail" -eq 0 ]]; then
  echo "==> All checks passed."
else
  echo "==> One or more checks FAILED." >&2
fi
exit "$fail"
