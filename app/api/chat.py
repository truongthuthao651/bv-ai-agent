"""OpenAI-compatible chat endpoint (STUB — Phase 1 placeholder).

Will implement ``POST /v1/chat/completions`` with SSE streaming so Open WebUI can
talk to it unmodified. Query flow: glossary expansion -> rewrite -> hybrid search
-> rerank -> generation (see the insurance-rag-pipeline skill, sections 5-6).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat/completions")
async def chat_completions() -> None:
    """TODO(phase-generation): implement retrieval + streaming generation."""
    raise HTTPException(status_code=501, detail="Not implemented yet")
