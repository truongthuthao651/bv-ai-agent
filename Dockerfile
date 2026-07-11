# =============================================================================
# FastAPI application image.
# python:3.12-slim + system pandoc (DOCX -> gfm+tex_math_dollars parsing path).
# =============================================================================
FROM python:3.12-slim

# System deps:
#   pandoc          — DOCX/OMML -> Markdown+LaTeX conversion
#   libgl1/libglib  — runtime libs PaddleOCR/OpenCV need
#   curl            — container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        pandoc \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Core deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# CPU-only torch from the PyTorch CPU index — avoids the ~5 GB CUDA stack that
# the default PyPI wheel bundles (useless on CPU-only hosts). Installed before
# the embedding stack so FlagEmbedding sees torch already satisfied and does not
# pull the CUDA build. The GPU override can layer a CUDA torch later if desired.
RUN pip install --no-cache-dir torch==2.12.1 \
        --index-url https://download.pytorch.org/whl/cpu

# Embedding (bge-m3 dense+sparse) + reranking + DOCX/XLSX parsing for the ingest slice.
COPY requirements-embed.txt .
RUN pip install --no-cache-dir -r requirements-embed.txt

# Heavy parsers (PDF/OCR) + eval — enabled in the hard-parser increment.
# Uncomment (and add a CPU torchvision) once those modules are implemented:
# RUN pip install --no-cache-dir torchvision==0.27.1 \
#         --index-url https://download.pytorch.org/whl/cpu
# COPY requirements-ml.txt .
# RUN pip install --no-cache-dir -r requirements-ml.txt

# App code.
COPY app ./app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
