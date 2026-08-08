#!/usr/bin/env bash
# =============================================================================
# Pull all models the stack needs. Works in BOTH deployment modes:
#   - native (no Docker): uses the local `ollama` CLI and .venv/bin/python
#     (created by scripts/setup_native.sh)
#   - docker: uses `docker compose exec` against the running containers
# Network access is allowed ONLY at this setup step (ollama pull + HF download).
# Reads model names from .env so weak machines can drop CHAT_MODEL to qwen3:4b.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ---- Load model names from .env (fall back to built-in defaults) ----
# Read one variable from .env. Never `source` it: values contain spaces and
# UTF-8 (ASSISTANT_NAME), which the shell would try to execute —
# under `set -e` that aborts the whole script.
env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

if [[ ! -f .env ]]; then
  echo "WARN: .env not found; using built-in defaults." >&2
fi

CHAT_MODEL="$(env_get CHAT_MODEL)"
CHAT_MODEL="${CHAT_MODEL:-qwen3:8b}"
VISION_MODEL="$(env_get VISION_MODEL)"
VISION_MODEL="${VISION_MODEL:-qwen2.5vl:7b}"
EMBED_MODEL="$(env_get EMBED_MODEL)"
EMBED_MODEL="${EMBED_MODEL:-bge-m3}"
RERANK_MODEL="$(env_get RERANK_MODEL)"
RERANK_MODEL="${RERANK_MODEL:-bge-reranker-v2-m3}"

# ---- Mode detection: a running compose api container means docker mode ----
MODE=native
if command -v docker >/dev/null 2>&1 \
    && [[ -n "$(docker compose ps -q api 2>/dev/null || true)" ]]; then
  MODE=docker
fi
echo "==> Mode: $MODE"

if [[ "$MODE" == "native" ]]; then
  if [[ ! -x .venv/bin/python ]]; then
    echo "ERROR: .venv not found — run 'bash scripts/setup_native.sh' first" >&2
    echo "       (or 'docker compose up -d' for docker mode)." >&2
    exit 1
  fi
  if ! command -v ollama >/dev/null 2>&1; then
    echo "ERROR: ollama CLI not found. Install it from https://ollama.com" >&2
    exit 1
  fi
fi

# Run a Python snippet (stdin) in the right place. Downloads land under
# ./models either way: relative paths resolve to the repo root natively and
# to WORKDIR /app (host-mounted ./models) inside the container.
run_py() {
  if [[ "$MODE" == "docker" ]]; then
    docker compose exec -T \
      -e HF_HUB_DISABLE_XET=1 -e HF_HUB_DOWNLOAD_TIMEOUT=60 \
      api python - "$@"
  else
    HF_HUB_DISABLE_XET=1 HF_HUB_DOWNLOAD_TIMEOUT=60 HF_HOME="$ROOT_DIR/models/hf" \
      .venv/bin/python - "$@"
  fi
}

# Ollama serves chat + vision. Embeddings/reranking use FlagEmbedding with local
# HF weights (bge-m3 must produce dense+sparse, which Ollama cannot).
echo "==> Pulling Ollama models"
for model in "$CHAT_MODEL" "$VISION_MODEL"; do
  echo "    - $model"
  if [[ "$MODE" == "docker" ]]; then
    docker compose exec -T ollama ollama pull "$model"
  else
    ollama pull "$model"
  fi
done

# ---- FlagEmbedding weights: bge-m3 (dense+sparse) + reranker, from Hugging Face ----
echo "==> Fetching embedding + reranker weights into ./models"
mkdir -p models
for model in "$EMBED_MODEL" "$RERANK_MODEL"; do
  echo "    - $model"
  run_py "$model" <<'PY'
import sys
from huggingface_hub import snapshot_download

model = sys.argv[1]
# BAAI publishes both bge-m3 and the reranker under the BAAI/ namespace.
repo = model if "/" in model else f"BAAI/{model}"
# FlagEmbedding uses the PyTorch weights + tokenizer (+ bge-m3's sparse/colbert
# linear layers). Skip ONNX/TF/Flax variants — large and unused.
path = snapshot_download(
    repo_id=repo,
    local_dir=f"models/{model}",
    ignore_patterns=[
        "*.onnx", "*.onnx_data", "onnx/*",
        "*.h5", "*.msgpack", "tf_*", "flax_*", "imgs/*",
    ],
)
print(f"      downloaded {repo} -> {path}")
PY
done

# ---- Docling weights (PDF layout/tableformer + formula model) ----
# Pre-fetched into ./models/docling so PDF parsing runs offline. Non-fatal:
# without it, the first PDF ingest downloads on demand into HF_HOME
# (./models/hf — still persistent, but needs network once).
echo "==> Fetching Docling PDF-model weights into ./models/docling"
if ! run_py <<'PY'
from pathlib import Path

target = Path("models/docling")
try:  # newer docling releases
    from docling.utils.model_downloader import download_models

    download_models(output_dir=target)
except ImportError:  # docling 2.15.x
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline

    StandardPdfPipeline.download_models_hf(local_dir=target)
print(f"      downloaded docling models -> {target}")
PY
then
  echo "WARN: docling model download failed; first PDF ingest will fetch on demand (needs network once)." >&2
fi

echo "==> Done. Verify with: bash scripts/healthcheck.sh"
