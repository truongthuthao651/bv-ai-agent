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
import re
import time
import uuid
from collections.abc import AsyncIterator

import httpx

from app.config.settings import settings
from app.generation.prompts import (
    REFUSAL_MESSAGE,
    SYSTEM_PROMPT,
    build_user_prompt,
    format_sources,
)
from app.models.schemas import ChatMessage, Hit

logger = logging.getLogger(__name__)

# Only recent turns are sent to the model — keeps the context window bounded
# for the small local model; retrieval already re-grounds each turn.
_MAX_HISTORY_TURNS = 6

_CONNECTION_ERROR_MESSAGE = (
    "Xin lỗi, hiện không thể kết nối tới mô hình sinh câu trả lời. "
    "Vui lòng thử lại sau."
)

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def strip_think(text: str) -> str:
    """Remove any complete ``<think>...</think>`` span from a full string."""
    return _THINK_BLOCK_RE.sub("", text).strip()


def _partial_tail_len(text: str, tag: str) -> int:
    """Length of the longest suffix of ``text`` that is a prefix of ``tag``.

    Lets the streaming stripper hold back a few chars in case a ``<think>`` /
    ``</think>`` tag is split across two token deltas.
    """
    for k in range(min(len(text), len(tag) - 1), 0, -1):
        if tag.startswith(text[-k:]):
            return k
    return 0


class ThinkStripper:
    """Incrementally drop ``<think>...</think>`` spans from a token stream.

    Reasoning models interleave their hidden chain-of-thought as ``<think>``
    tags in the content stream; we never want that in the user-facing answer.
    ``feed`` returns only the display-safe text seen so far, buffering partial
    tags across deltas so a tag split mid-token isn't missed.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def feed(self, text: str) -> str:
        self._buf += text
        out: list[str] = []
        while self._buf:
            if not self._in_think:
                idx = self._buf.find(_THINK_OPEN)
                if idx == -1:
                    keep = _partial_tail_len(self._buf, _THINK_OPEN)
                    out.append(self._buf[: len(self._buf) - keep])
                    self._buf = self._buf[len(self._buf) - keep :]
                    break
                out.append(self._buf[:idx])
                self._buf = self._buf[idx + len(_THINK_OPEN) :]
                self._in_think = True
            else:
                idx = self._buf.find(_THINK_CLOSE)
                if idx == -1:
                    keep = _partial_tail_len(self._buf, _THINK_CLOSE)
                    self._buf = self._buf[len(self._buf) - keep :]
                    break
                self._buf = self._buf[idx + len(_THINK_CLOSE) :]
                self._in_think = False
        return "".join(out)

    def flush(self) -> str:
        """Emit any trailing buffered text (unless we ended inside a think span)."""
        if self._in_think:
            return ""
        out, self._buf = self._buf, ""
        return out


def build_messages(
    query: str, hits: list[Hit], history: list[ChatMessage] | None = None
) -> list[dict[str, str]]:
    """Build the Ollama ``messages`` array: system + trimmed history + grounded user turn."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-_MAX_HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": build_user_prompt(query, hits)})
    return messages


def _ollama_payload(
    messages: list[dict[str, str]], *, stream: bool
) -> dict[str, object]:
    """Build the Ollama ``/api/chat`` request body.

    ``think`` is sent explicitly so reasoning models (qwen3) skip their hidden
    chain-of-thought when ``settings.llm_thinking`` is False — the single biggest
    latency win on CPU-only setups.
    """
    return {
        "model": settings.chat_model,
        "messages": messages,
        "stream": stream,
        "think": settings.llm_thinking,
        # Without this Ollama unloads the model after ~5 idle minutes and the
        # next question pays a full reload; see settings.ollama_keep_alive.
        "keep_alive": settings.ollama_keep_alive,
        "options": {
            "temperature": settings.llm_temperature,
            "num_predict": settings.llm_max_tokens,
        },
    }


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


def _is_refusal(answer: str) -> bool:
    """True when the answer is (or contains) the mandated refusal sentence."""
    return REFUSAL_MESSAGE.rstrip(".") in answer


def _sources_suffix(answer: str, hits: list[Hit]) -> str:
    """The sources block to append after ``answer``, or "" when inapplicable.

    Refusals and error messages get no sources — listing documents under an
    "I couldn't find it" answer would look like a contradiction.
    """
    if not answer.strip() or not hits or _is_refusal(answer):
        return ""
    return f"\n\n{format_sources(hits)}"


async def stream_static_answer(text: str) -> AsyncIterator[str]:
    """Stream a fixed message as OpenAI SSE chunks (deterministic refusal path)."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    model = settings.chat_model
    yield _sse_chunk(completion_id, model, {"role": "assistant"}, None)
    yield _sse_chunk(completion_id, model, {"content": text}, None)
    yield _sse_chunk(completion_id, model, {}, "stop")
    yield "data: [DONE]\n\n"


async def stream_answer(
    query: str, hits: list[Hit], history: list[ChatMessage] | None = None
) -> AsyncIterator[str]:
    """Stream the assistant's answer as SSE lines (OpenAI ``chat.completion.chunk``)."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    model = settings.chat_model
    messages = build_messages(query, hits, history)

    yield _sse_chunk(completion_id, model, {"role": "assistant"}, None)

    stripper = ThinkStripper()
    answer_parts: list[str] = []
    started = time.perf_counter()
    first_token_at: float | None = None
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/api/chat",
                json=_ollama_payload(messages, stream=True),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    content, done = parse_ollama_line(line)
                    if content:
                        visible = stripper.feed(content)
                        if visible:
                            if first_token_at is None:
                                first_token_at = time.perf_counter()
                            answer_parts.append(visible)
                            yield _sse_chunk(
                                completion_id, model, {"content": visible}, None
                            )
                    if done:
                        break
        tail = stripper.flush()
        if tail:
            answer_parts.append(tail)
            yield _sse_chunk(completion_id, model, {"content": tail}, None)
        suffix = _sources_suffix("".join(answer_parts), hits)
        if suffix:
            yield _sse_chunk(completion_id, model, {"content": suffix}, None)
        total_ms = (time.perf_counter() - started) * 1000
        first_ms = (
            (first_token_at - started) * 1000 if first_token_at is not None else -1.0
        )
        logger.info(
            "generation timings: first_token=%.0fms total=%.0fms", first_ms, total_ms
        )
    except httpx.HTTPError as exc:
        logger.error("Generation failed: %s", exc)
        yield _sse_chunk(
            completion_id, model, {"content": _CONNECTION_ERROR_MESSAGE}, None
        )

    yield _sse_chunk(completion_id, model, {}, "stop")
    yield "data: [DONE]\n\n"


def preload_model() -> None:
    """Load the chat model into Ollama's memory ahead of the first user request.

    An empty-prompt ``/api/generate`` call makes Ollama load (and keep alive) the
    model without generating tokens — on CPU the model load is the single biggest
    slice of first-request latency. Raises ``httpx.HTTPError`` on failure so the
    caller can log it; warmup treats that as non-fatal.
    """
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/generate",
        json={
            "model": settings.chat_model,
            "prompt": "",
            "stream": False,
            "think": False,
            "keep_alive": settings.ollama_keep_alive,
        },
        timeout=settings.ollama_timeout,
    )
    resp.raise_for_status()


def generate_answer(
    query: str, hits: list[Hit], history: list[ChatMessage] | None = None
) -> str:
    """Non-streaming variant: block for the full answer (``stream: false`` requests)."""
    messages = build_messages(query, hits, history)
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json=_ollama_payload(messages, stream=False),
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        answer = strip_think(content)
        return answer + _sources_suffix(answer, hits)
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Generation failed: %s", exc)
        return _CONNECTION_ERROR_MESSAGE
