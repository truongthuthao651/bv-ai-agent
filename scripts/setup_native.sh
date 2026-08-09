#!/usr/bin/env bash
# =============================================================================
# One-time NATIVE (no-Docker) setup for macOS / Linux.
#
# Installs everything into one virtualenv inside the repo — no system-wide
# software beyond Python 3.11/3.12 and Ollama (https://ollama.com):
#   .venv — the FastAPI app AND frontend (pandoc arrives bundled via
#           pypandoc-binary; the vector DB runs EMBEDDED in-process, so no
#           Qdrant server; the landing/admin/chat UI is served from the same
#           process — see frontend/ for the dev-machine-only build step)
# Then pulls all model weights via scripts/setup_models.sh.
#
# Network access is needed ONLY during this script (pip + model downloads);
# afterwards the stack runs fully offline via scripts/run_native.sh.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ---- Pick a Python: pinned to 3.11/3.12 (see TEAMMATE_GUIDE.md) ----
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
  echo "ERROR: need Python 3.11 or 3.12 on PATH." >&2
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

# ---- Frontend build (dev-machine only — see frontend/, TEAMMATE_GUIDE.md) ----
# Skipped here if Node isn't installed: the committed app/static/dist/ still
# works for deployment; only rebuild when you've actually changed frontend/.
if command -v npm >/dev/null 2>&1; then
  echo "==> Building frontend (frontend/ -> app/static/dist/)"
  (cd frontend && npm install && npm run build)
else
  echo "WARN: npm not found — skipping frontend build. app/static/dist/ (already" >&2
  echo "      committed) will be served as-is; install Node to rebuild it." >&2
fi

# ---- Model weights (Ollama models + HF embedding/reranker/docling) ----
bash scripts/setup_models.sh

echo "==> Native setup complete."
echo "    Provision an account:  .venv/bin/python scripts/seed_accounts.py you@baoviet.com PASSWORD admin"
echo "    Start the stack:       bash scripts/run_native.sh"
echo "    Check health:          bash scripts/healthcheck.sh"
echo "    Stop the stack:        bash scripts/stop_native.sh"
