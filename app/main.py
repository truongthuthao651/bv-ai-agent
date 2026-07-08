"""FastAPI entrypoint.

Wires up routers and application lifespan (model warmup): ``/health``, ``/ingest``
+ ``/documents`` (Markdown/DOCX), and the OpenAI-compatible ``/v1/chat/completions``.
Hard parsers (PDF/XLSX/image) arrive in the hard-parser increment (Increment D).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, health, ingest
from app.config.settings import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("insurance-assistant")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan.

    TODO(phase-later): warm up Ollama models (chat/vision/embeddings) and ensure
    the Qdrant collection exists so the first user request isn't cold. Kept as a
    no-op in Phase 1 to keep startup dependency-free for `import app.main`.
    """
    logger.info("Starting insurance-assistant API (chat_model=%s)", settings.chat_model)
    yield
    logger.info("Shutting down insurance-assistant API")


app = FastAPI(
    title="Local Insurance RAG Assistant",
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
