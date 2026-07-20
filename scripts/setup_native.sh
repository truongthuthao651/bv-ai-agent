#!/usr/bin/env bash
# =============================================================================
# One-time NATIVE (no-Docker) setup for macOS / Linux.
#
# Installs everything into two virtualenvs inside the repo — no system-wide
# software beyond Python 3.11/3.12 and Ollama (https://ollama.com):
#   .venv        — the FastAPI app (pandoc arrives bundled via pypandoc-binary;
#                  the vector DB runs EMBEDDED in-process, so no Qdrant server)
#   .venv-webui  — Open WebUI (big dependency tree; kept apart from the app's)
# Then pulls all model weights via scripts/setup_models.sh.
#
# Network access is needed ONLY during this script (pip + model downloads);
# afterwards the stack runs fully offline via scripts/run_native.sh.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ---- Pick a Python: Open WebUI 0.5.4 requires >=3.11,<3.13 ----
PYTHON=""
for cand in python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info < (3, 13) else 1)'; then
      PYTHON="$cand"
      break
    fi
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "ERROR: need Python 3.11 or 3.12 on PATH (Open WebUI does not support 3.13 yet)." >&2
  echo "       Install from https://www.python.org/downloads/ and re-run." >&2
  exit 1
fi
echo "==> Using $($PYTHON --version) ($(command -v "$PYTHON"))"

if ! command -v ollama >/dev/null 2>&1; then
  echo "WARN: ollama not found on PATH. Install it from https://ollama.com" >&2
  echo "      (needed to serve the chat/vision models; re-run this script after)." >&2
fi

if [[ ! -f .env ]]; then
  echo "==> Creating .env from .env.example (edit it for this machine if needed)"
  cp .env.example .env
fi

# ---- App venv (install order mirrors the Dockerfile: CPU torch BEFORE the
#      embedding stack so FlagEmbedding/docling never pull the CUDA build) ----
echo "==> Creating app venv (.venv) and installing pinned requirements"
[[ -d .venv ]] || "$PYTHON" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements-embed.txt
.venv/bin/pip install torchvision==0.27.1 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements-pdf.txt

# ---- Open WebUI venv (version pinned to match the compose image tag) ----
echo "==> Creating Open WebUI venv (.venv-webui)"
[[ -d .venv-webui ]] || "$PYTHON" -m venv .venv-webui
.venv-webui/bin/pip install --upgrade pip
.venv-webui/bin/pip install open-webui==0.5.4

# ---- Bảo Việt branding (logo, colors, VI prompt suggestions) ----
# Patches the installed Open WebUI package in place; also re-run automatically
# by run_native.sh before each start (pip upgrades restore stock assets).
.venv/bin/python scripts/open_webui/apply_branding.py || true

# ---- Model weights (Ollama models + HF embedding/reranker/docling) ----
bash scripts/setup_models.sh

echo "==> Native setup complete."
echo "    Start the stack:   bash scripts/run_native.sh"
echo "    (Run it once now, while still online: Open WebUI fetches a small"
echo "     internal model on first start; afterwards everything is offline.)"
echo "    Check health:      bash scripts/healthcheck.sh"
echo "    Stop the stack:    bash scripts/stop_native.sh"
