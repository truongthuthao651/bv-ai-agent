"""OpenAI-compatible chat endpoint.

``POST /v1/chat/completions`` implements the full query flow (skill, sections
5-6): standalone-question rewrite -> glossary expansion -> hybrid search ->
rerank -> generation. Streams SSE in OpenAI format by default so Open WebUI
works unmodified; also supports ``stream: false`` for plain API clients.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.config.settings import settings
from app.generation import generator
from app.generation.prompts import REFUSAL_MESSAGE
from app.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Hit,
    ModelCard,
    ModelList,
)
from app.retrieval.query_expansion import expand_query
from app.retrieval.query_rewrite import rewrite_standalone
from app.retrieval.reranker import rerank
from app.retrieval.retriever import hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["chat"])


@router.get("/models", response_model=ModelList)
async def list_models() -> ModelList:
    """Advertise the single branded assistant model.

    Open WebUI calls this to populate its model dropdown; without it our backend
    contributes no selectable model and the chat UI stays empty. The id/label are
    branding only — ``chat_completions`` always serves ``settings.chat_model``.
    """
    return ModelList(
        data=[
            ModelCard(
                id=settings.assistant_model_id,
                created=int(time.time()),
                name=settings.assistant_name,
            )
        ]
    )


def _split_request(request: ChatCompletionRequest) -> tuple[str, list[ChatMessage]]:
    """Split ``messages`` into (latest user turn, prior history)."""
    if not request.messages:
        return "", []
    *history, last = request.messages
    return last.content, history


def _retrieve(query: str, history: list[ChatMessage]) -> tuple[str, list[Hit]]:
    """Run rewrite -> expansion -> hybrid search -> rerank; each stage is self-gating.

    Logs per-stage wall time so slow answers can be attributed to a stage
    instead of guessed at. eval/run_ragas.py mirrors this flow stage-by-stage —
    keep the two in sync when the query flow changes.
    """
    t0 = time.perf_counter()
    standalone_query = rewrite_standalone(history, query)
    t1 = time.perf_counter()
    search_query = expand_query(standalone_query)
    t2 = time.perf_counter()
    hits = hybrid_search(search_query)
    t3 = time.perf_counter()
    hits = rerank(standalone_query, hits)
    t4 = time.perf_counter()
    logger.info(
        "retrieval timings: rewrite=%.0fms expand=%.0fms search=%.0fms "
        "rerank=%.0fms hits=%d",
        (t1 - t0) * 1000,
        (t2 - t1) * 1000,
        (t3 - t2) * 1000,
        (t4 - t3) * 1000,
        len(hits),
    )
    return standalone_query, hits


@router.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Answer a chat request, grounded only in retrieved document chunks."""
    query, history = _split_request(request)
    standalone_query, hits = await run_in_threadpool(_retrieve, query, history)

    # No hit survived the reranker's relevance floor: refuse deterministically
    # instead of handing the LLM irrelevant context and hoping it refuses.
    if not hits:
        if request.stream:
            return StreamingResponse(
                generator.stream_static_answer(REFUSAL_MESSAGE),
                media_type="text/event-stream",
            )
        answer = REFUSAL_MESSAGE
    elif request.stream:
        return StreamingResponse(
            generator.stream_answer(standalone_query, hits, history),
            media_type="text/event-stream",
        )
    else:
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
