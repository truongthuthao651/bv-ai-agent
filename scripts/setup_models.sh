#!/usr/bin/env bash
# =============================================================================
# Download the Ollama, embedding, reranking, and Docling models for the native
# stack. Network access is required only during this setup step.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

venv_python() {
  if [[ -x .venv/bin/python ]]; then
    printf '%s\n' .venv/bin/python
  elif [[ -f .venv/Scripts/python.exe ]]; then
    printf '%s\n' .venv/Scripts/python.exe
  else
    return 1
  fi
}

if [[ ! -f .env ]]; then
  echo "WARN: .env not found; using built-in model defaults." >&2
fi

CHAT_MODEL="$(env_get CHAT_MODEL)";     CHAT_MODEL="${CHAT_MODEL:-qwen3:8b}"
VISION_MODEL="$(env_get VISION_MODEL)"; VISION_MODEL="${VISION_MODEL:-qwen2.5vl:7b}"
EMBED_MODEL="$(env_get EMBED_MODEL)";   EMBED_MODEL="${EMBED_MODEL:-bge-m3}"
RERANK_MODEL="$(env_get RERANK_MODEL)"; RERANK_MODEL="${RERANK_MODEL:-bge-reranker-v2-m3}"

APP_PYTHON="$(venv_python || true)"
if [[ -z "$APP_PYTHON" ]]; then
  echo "ERROR: .venv is missing or unusable; run bash scripts/setup_native.sh first." >&2
  exit 1
fi
if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama CLI not found. Install it from https://ollama.com." >&2
  exit 1
fi

run_py() {
  HF_HUB_DISABLE_XET=1 HF_HUB_DOWNLOAD_TIMEOUT=60 HF_HOME="$ROOT_DIR/models/hf" \
    "$APP_PYTHON" - "$@"
}

echo "==> Pulling Ollama models"
for model in "$CHAT_MODEL" "$VISION_MODEL"; do
  echo "    - $model"
  ollama pull "$model"
done

echo "==> Fetching embedding and reranker weights into ./models"
mkdir -p models
for model in "$EMBED_MODEL" "$RERANK_MODEL"; do
  echo "    - $model"
  run_py "$model" <<'PY'
import sys
from huggingface_hub import snapshot_download

model = sys.argv[1]
repo = model if "/" in model else f"BAAI/{model}"
path = snapshot_download(
    repo_id=repo,
    local_dir=f"models/{model}",
    ignore_patterns=[
        "*.onnx", "*.onnx_data", "onnx/*", "*.h5", "*.msgpack",
        "tf_*", "flax_*", "imgs/*",
    ],
)
print(f"      downloaded {repo} -> {path}")
PY
done

echo "==> Fetching Docling PDF-model weights into ./models/docling"
if ! run_py <<'PY'
from pathlib import Path

target = Path("models/docling")
try:
    from docling.utils.model_downloader import download_models
    download_models(output_dir=target)
except ImportError:
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    StandardPdfPipeline.download_models_hf(local_dir=target)
print(f"      downloaded docling models -> {target}")
PY
then
  echo "WARN: Docling model download failed; first PDF ingestion will need network access." >&2
fi

echo "==> Done. Verify with: bash scripts/healthcheck.sh"
