#!/usr/bin/env bash
# =============================================================================
# One-time native setup for the local RAG stack.
#
# UV is preferred. If it is unavailable, the script falls back to Python 3.11
# or 3.12 with venv/pip. Both the FastAPI app and Open WebUI get separate,
# repository-local environments so no project dependency is system-installed.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

find_python() {
  local candidate
  for candidate in python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 13)))'; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

venv_python() {
  local venv_dir="$1"
  if [[ -x "$venv_dir/bin/python" ]]; then
    printf '%s\n' "$venv_dir/bin/python"
  elif [[ -f "$venv_dir/Scripts/python.exe" ]]; then
    printf '%s\n' "$venv_dir/Scripts/python.exe"
  else
    return 1
  fi
}

create_venv() {
  local venv_dir="$1"
  if [[ -e "$venv_dir" ]]; then
    if ! venv_python "$venv_dir" >/dev/null; then
      echo "ERROR: $venv_dir exists but is not a usable virtual environment." >&2
      echo "       Move it aside or remove it manually, then re-run this script." >&2
      exit 1
    fi
    return
  fi

  if [[ "$SETUP_TOOL" == "uv" ]]; then
    uv venv --python 3.12 "$venv_dir"
  else
    "$FALLBACK_PYTHON" -m venv "$venv_dir"
  fi
}

install_into() {
  local python_path="$1"
  shift
  if [[ "$SETUP_TOOL" == "uv" ]]; then
    uv pip install --python "$python_path" "$@"
  else
    "$python_path" -m pip install "$@"
  fi
}

if command -v uv >/dev/null 2>&1; then
  SETUP_TOOL="uv"
  FALLBACK_PYTHON=""
  echo "==> Using uv ($(uv --version))"
else
  SETUP_TOOL="python"
  FALLBACK_PYTHON="$(find_python || true)"
  if [[ -z "$FALLBACK_PYTHON" ]]; then
    echo "ERROR: uv is unavailable and no supported Python 3.11/3.12 interpreter was found." >&2
    exit 1
  fi
  echo "==> uv not found; using $FALLBACK_PYTHON ($("$FALLBACK_PYTHON" --version))"
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama CLI not found. Install it from https://ollama.com and re-run." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "==> Creating .env from .env.example (edit it for this machine if needed)"
  cp .env.example .env
fi

echo "==> Preparing app environment (.venv)"
create_venv .venv
APP_PYTHON="$(venv_python .venv)"
"$APP_PYTHON" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 13)))' \
  || { echo "ERROR: .venv must use Python 3.11 or 3.12." >&2; exit 1; }

# Keep this order: CPU torch must be installed before the embedding/PDF stacks
# so their dependencies do not select a CUDA build on CPU-only machines.
install_into "$APP_PYTHON" -r requirements.txt
install_into "$APP_PYTHON" torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu
install_into "$APP_PYTHON" torchvision==0.27.1 --index-url https://download.pytorch.org/whl/cpu
install_into "$APP_PYTHON" -r requirements-embed.txt
install_into "$APP_PYTHON" -r requirements-pdf.txt

echo "==> Preparing Open WebUI environment (.venv-webui)"
create_venv .venv-webui
WEBUI_PYTHON="$(venv_python .venv-webui)"
"$WEBUI_PYTHON" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 13)))' \
  || { echo "ERROR: .venv-webui must use Python 3.11 or 3.12." >&2; exit 1; }
install_into "$WEBUI_PYTHON" open-webui==0.5.4

# Branding is idempotent and run again before each Open WebUI start.
"$WEBUI_PYTHON" scripts/open_webui/apply_branding.py || true

echo "==> Downloading local model weights"
bash scripts/setup_models.sh

echo "==> Native setup complete."
echo "    Start:  bash scripts/run_native.sh"
echo "    Check:  bash scripts/healthcheck.sh"
echo "    Stop:   bash scripts/stop_native.sh"
