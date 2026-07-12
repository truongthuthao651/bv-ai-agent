"""FastAPI entrypoint.

Wires up routers and application lifespan (model warmup): ``/health``, ``/ingest``
+ ``/documents`` (Markdown/DOCX/XLSX/PDF/glossary), and the OpenAI-compatible
``/v1/chat/completions``. Scanned-image OCR arrives with the OCR increment.

Also serves a small dependency-free admin UI (``app/static/index.html``) at ``/``
for uploading documents and smoke-testing chat — Open WebUI (port 3000) has no
notion of our custom ``/ingest`` endpoint, so this fills that gap without adding
a frontend framework or any external/CDN dependency (must stay air-gapped).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.api import chat, health, ingest
from app.config.settings import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("insurance-assistant")


async def _warmup() -> None:
    """Best-effort pre-load of the lazily-initialized, slow-to-start pieces.

    Ensures the Qdrant collection exists and loads the bge-m3 embedder, the
    reranker, and the Ollama chat model up front so the first real request isn't
    cold. Each step is isolated in its own ``try`` and blocking work is pushed to
    a threadpool: a missing service or model weights degrades to a logged warning
    rather than a failed startup (e.g. on a dev box without weights downloaded).
    """
    # Imported here (not at module load) so importing app.main stays cheap and
    # free of the heavy embedding/reranking dependencies.
    from app.generation import generator
    from app.ingestion import indexer
    from app.retrieval import reranker

    steps = (
        ("Qdrant collection", indexer.ensure_collection),
        ("bge-m3 embedder", indexer.get_embedder),
        ("reranker", reranker.get_reranker),
        ("Ollama chat model", generator.preload_model),
    )
    for label, fn in steps:
        try:
            await run_in_threadpool(fn)
            logger.info("Warmup: %s ready", label)
        except Exception as exc:  # noqa: BLE001 - warmup must never break startup
            logger.warning(
                "Warmup: %s unavailable (%s); will load on demand", label, exc
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: optional warmup on startup (see ``_warmup``)."""
    logger.info("Starting insurance-assistant API (chat_model=%s)", settings.chat_model)
    if settings.warmup_on_startup:
        await _warmup()
    yield
    logger.info("Shutting down insurance-assistant API")


app = FastAPI(
    title="Trợ lý AI Bảo Việt Life — Local RAG API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(ingest.router)

# Mounted last so it only catches paths not matched by an API route above
# (e.g. "/", "/index.html") and doesn't shadow /health, /ingest, etc.
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
    name="admin-ui",
)
