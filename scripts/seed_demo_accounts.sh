#!/usr/bin/env bash
# Seed demo accounts for local development / presentations.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PY="${ROOT_DIR}/.venv/bin/python"
elif [[ -f "${ROOT_DIR}/.venv/Scripts/python.exe" ]]; then
  PY="${ROOT_DIR}/.venv/Scripts/python.exe"
else
  echo "ERROR: .venv not found — run scripts/setup_native.sh first." >&2
  exit 1
fi
"$PY" scripts/seed_accounts.py admin@baoviet.com.vn 'Admin123!' admin
echo ""
echo "Demo admin: admin@baoviet.com.vn / Admin123!"
echo "Employees: sign up at /login with any @baoviet.com.vn email."
