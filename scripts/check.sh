#!/usr/bin/env bash
# =============================================================================
# Local CI-equivalent (MAINT3, 2026-08-05 audit): there is no hosted runner
# for this repo, so nothing enforces `ruff check`/`pytest` passing before a
# commit lands except a developer remembering to run them by hand. Run this
# before committing (or wire it into a pre-commit hook) to catch what CI
# would have caught. Exits non-zero on the first failing step.
# =============================================================================
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

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

step "ruff check"        ruff check app/ tests/ eval/ scripts/
step "ruff format --check" ruff format --check app/ tests/ eval/ scripts/
step "pytest"            pytest tests/ -x -q

if [[ "$fail" -eq 0 ]]; then
  echo "==> All checks passed."
else
  echo "==> One or more checks FAILED." >&2
fi
exit "$fail"
