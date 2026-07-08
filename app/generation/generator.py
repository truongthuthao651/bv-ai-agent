"""Generation: assemble context, call Ollama, stream OpenAI-compatible SSE.

Builds the chat message list (system prompt + trimmed history + the user turn
with numbered context from ``display_text``), calls the local Ollama chat
model, and streams tokens as ``chat.completion.chunk`` SSE lines so Open WebUI
works unmodified. LaTeX in ``display_text`` passes through untouched — Open
WebUI renders it with KaTeX (skill, section 6).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator

import httpx

from app.config.settings import settings
from app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.models.schemas import ChatMessage, Hit

logger = logging.getLogger(__name__)

# Only recent turns are sent to the model — keeps the context window bounded
# for the small local model; retrieval already re-grounds each turn.
_MAX_HISTORY_TURNS = 6

_CONNECTION_ERROR_MESSAGE = (
    "Xin lỗi, hiện không thể kết nối tới mô hình sinh câu trả lời. "
    "Vui lòng thử lại sau."
)


def build_messages(
    query: str, hits: list[Hit], history: list[ChatMessage] | None = None
) -> list[dict[str, str]]:
    """Build the Ollama ``messages`` array: system + trimmed history + grounded user turn."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-_MAX_HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": build_user_prompt(query, hits)})
    return messages


def _sse_chunk(
    completion_id: str, model: str, delta: dict[str, str], finish_reason: str | None
) -> str:
    """Format one OpenAI ``chat.completion.chunk`` as an SSE ``data:`` line."""
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def parse_ollama_line(line: str) -> tuple[str, bool]:
    """Parse one NDJSON line from Ollama ``/api/chat``; returns (content_delta, done).

    Pulled out as a pure function so the streaming parse logic is unit-testable
    without a running Ollama.
    """
    data = json.loads(line)
    content = data.get("message", {}).get("content", "")
    return content, bool(data.get("done"))


async def stream_answer(
    query: str, hits: list[Hit], history: list[ChatMessage] | None = None
) -> AsyncIterator[str]:
    """Stream the assistant's answer as SSE lines (OpenAI ``chat.completion.chunk``)."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    model = settings.chat_model
    messages = build_messages(query, hits, history)

    yield _sse_chunk(completion_id, model, {"role": "assistant"}, None)

    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": settings.llm_temperature,
                        "num_predict": settings.llm_max_tokens,
                    },
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    content, done = parse_ollama_line(line)
                    if content:
                        yield _sse_chunk(
                            completion_id, model, {"content": content}, None
                        )
                    if done:
                        break
    except httpx.HTTPError as exc:
        logger.error("Generation failed: %s", exc)
        yield _sse_chunk(
            completion_id, model, {"content": _CONNECTION_ERROR_MESSAGE}, None
        )

    yield _sse_chunk(completion_id, model, {}, "stop")
    yield "data: [DONE]\n\n"


def generate_answer(
    query: str, hits: list[Hit], history: list[ChatMessage] | None = None
) -> str:
    """Non-streaming variant: block for the full answer (``stream: false`` requests)."""
    messages = build_messages(query, hits, history)
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.chat_model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": settings.llm_temperature,
                    "num_predict": settings.llm_max_tokens,
                },
            },
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Generation failed: %s", exc)
        return _CONNECTION_ERROR_MESSAGE
