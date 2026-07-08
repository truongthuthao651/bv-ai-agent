"""OpenAI-compatible chat endpoint.

``POST /v1/chat/completions`` implements the full query flow (skill, sections
5-6): standalone-question rewrite -> glossary expansion -> hybrid search ->
rerank -> generation. Streams SSE in OpenAI format by default so Open WebUI
works unmodified; also supports ``stream: false`` for plain API clients.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.config.settings import settings
from app.generation import generator
from app.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Hit,
)
from app.retrieval.query_expansion import expand_query
from app.retrieval.query_rewrite import rewrite_standalone
from app.retrieval.reranker import rerank
from app.retrieval.retriever import hybrid_search

router = APIRouter(prefix="/v1", tags=["chat"])


def _split_request(request: ChatCompletionRequest) -> tuple[str, list[ChatMessage]]:
    """Split ``messages`` into (latest user turn, prior history)."""
    if not request.messages:
        return "", []
    *history, last = request.messages
    return last.content, history


def _retrieve(query: str, history: list[ChatMessage]) -> tuple[str, list[Hit]]:
    """Run rewrite -> expansion -> hybrid search -> rerank; each stage is self-gating."""
    standalone_query = rewrite_standalone(history, query)
    search_query = expand_query(standalone_query)
    hits = hybrid_search(search_query)
    hits = rerank(standalone_query, hits)
    return standalone_query, hits


@router.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Answer a chat request, grounded only in retrieved document chunks."""
    query, history = _split_request(request)
    standalone_query, hits = await run_in_threadpool(_retrieve, query, history)

    if request.stream:
        return StreamingResponse(
            generator.stream_answer(standalone_query, hits, history),
            media_type="text/event-stream",
        )

    answer = await run_in_threadpool(
        generator.generate_answer, standalone_query, hits, history
    )
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=settings.chat_model,
        choices=[
            ChatCompletionChoice(message=ChatMessage(role="assistant", content=answer))
        ],
    )
