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
from collections.abc import AsyncIterator, Callable

import httpx

from app.config.settings import settings
from app.generation.prompts import (
    ADVISORY_DISCLAIMER,
    CALC_DISCLAIMER,
    GENERAL_KNOWLEDGE_DISCLAIMER,
    GENERAL_KNOWLEDGE_HEADING,
    HYBRID_DISCLAIMER,
    HYBRID_SYSTEM_PROMPT,
    REFUSAL_MESSAGE,
    build_user_prompt,
    format_sources,
    system_prompt,
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
    query: str,
    hits: list[Hit],
    history: list[ChatMessage] | None = None,
    *,
    advisory: bool = False,
) -> list[dict[str, str]]:
    """Build the Ollama ``messages`` array: system + trimmed history + grounded user turn.

    ``advisory`` selects the synthesis-permitting variant of the grounded system
    prompt (comparison / "which should the customer pick?" turns).
    """
    messages = [{"role": "system", "content": system_prompt(advisory=advisory)}]
    for turn in (history or [])[-_MAX_HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": build_user_prompt(query, hits)})
    return messages


def build_hybrid_messages(
    query: str, history: list[ChatMessage] | None = None
) -> list[dict[str, str]]:
    """Messages for the no-context, general-knowledge fallback (empty retrieval).

    Unlike ``build_messages``, the user turn is the raw query — there's no
    retrieved context to number and prepend.
    """
    messages = [{"role": "system", "content": HYBRID_SYSTEM_PROMPT}]
    for turn in (history or [])[-_MAX_HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": query})
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


_MATH_SPAN_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.DOTALL)
# A concrete numeric value (decimal or 2+ digits) — as opposed to structural
# constants like the "1" in $A_x = 1 - d\ddot{a}_x$.
_NUMERIC_VALUE_RE = re.compile(r"\d[.,]\d|\d{2,}")


def _needs_calc_disclaimer(answer: str) -> bool:
    """True when the answer presents computed numbers (answering rule 4).

    Triggers on approximate-result markers or concrete numeric values inside
    LaTeX math spans (substitution steps). Plain-text figures quoted from a
    document ("60 ngày") deliberately do NOT trigger — the disclaimer is about
    the model's own arithmetic, not about cited values.
    """
    if "\\approx" in answer or "≈" in answer:
        return True
    return any(_NUMERIC_VALUE_RE.search(span) for span in _MATH_SPAN_RE.findall(answer))


def _disclaimer_suffix(answer: str) -> str:
    """The calculation disclaimer to append, or "" when absent-by-design.

    Deterministic guardrail: a small local model both miscalculates and forgets
    instructions, so rule 4's disclaimer is enforced here rather than trusted
    to the prompt. No-op when the model already included the sentence.
    """
    if not answer.strip() or _is_refusal(answer):
        return ""
    if CALC_DISCLAIMER.rstrip(".") in answer:
        return ""
    if not _needs_calc_disclaimer(answer):
        return ""
    return f"\n\n{CALC_DISCLAIMER}"


def _hybrid_disclaimer_suffix(answer: str) -> str:
    """The "general knowledge, not company documents" label for hybrid answers.

    Same guardrail pattern as ``_disclaimer_suffix``: enforced here rather than
    trusted to the prompt, since a small local model forgets instructions.
    No-op for refusals/empty answers (nothing to label) or if already present.
    """
    if not answer.strip() or _is_refusal(answer):
        return ""
    if HYBRID_DISCLAIMER in answer:
        return ""
    return f"\n\n_{HYBRID_DISCLAIMER}_"


def _advisory_disclaimer_suffix(answer: str) -> str:
    """The "this is a synthesis, not official advice" label for advisory answers.

    Same guardrail pattern as the other disclaimers: enforced in code, not
    trusted to the prompt. No-op for refusals/empty answers or if already present.
    """
    if not answer.strip() or _is_refusal(answer):
        return ""
    if ADVISORY_DISCLAIMER in answer:
        return ""
    return f"\n\n_{ADVISORY_DISCLAIMER}_"


def _general_knowledge_suffix(answer: str) -> str:
    """Label the optional "Kiến thức chung" section when the model produced one.

    The section is fenced behind a fixed heading (GENERAL_KNOWLEDGE_HEADING);
    when it's present, the answer mixes document-sourced content with the
    model's own knowledge, so the boundary gets stated explicitly rather than
    left to the heading alone. No-op when the model skipped the section.
    """
    if not answer.strip() or _is_refusal(answer):
        return ""
    if GENERAL_KNOWLEDGE_HEADING not in answer:
        return ""
    if GENERAL_KNOWLEDGE_DISCLAIMER in answer:
        return ""
    return f"\n\n_{GENERAL_KNOWLEDGE_DISCLAIMER}_"


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


async def _stream_chat(
    messages: list[dict[str, str]], suffix_fn: Callable[[str], str]
) -> AsyncIterator[str]:
    """Shared Ollama-streaming core: SSE chunks + a deterministic suffix.

    ``suffix_fn`` computes whatever must be appended after the model's own
    text (calc disclaimer + sources for grounded answers, the "general
    knowledge" label for hybrid ones) — kept a parameter so both answer paths
    share the exact same streaming/think-stripping/error-handling logic.
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    model = settings.chat_model

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
        body = "".join(answer_parts)
        suffix = suffix_fn(body)
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


def _grounded_suffix_fn(hits: list[Hit], advisory: bool) -> Callable[[str], str]:
    """Suffixes appended after a grounded answer, in reading order.

    Calculation disclaimer, then the advisory label, then the general-knowledge
    label, then the sources block — the sources stay last so the numbered
    citations remain the final thing on screen.
    """

    def suffix_fn(body: str) -> str:
        out = _disclaimer_suffix(body)
        if advisory:
            out += _advisory_disclaimer_suffix(body)
        out += _general_knowledge_suffix(body)
        return out + _sources_suffix(body, hits)

    return suffix_fn


async def stream_answer(
    query: str,
    hits: list[Hit],
    history: list[ChatMessage] | None = None,
    *,
    advisory: bool = False,
) -> AsyncIterator[str]:
    """Stream the assistant's grounded answer as SSE lines."""
    messages = build_messages(query, hits, history, advisory=advisory)
    async for chunk in _stream_chat(messages, _grounded_suffix_fn(hits, advisory)):
        yield chunk


async def stream_hybrid_answer(
    query: str, history: list[ChatMessage] | None = None
) -> AsyncIterator[str]:
    """Stream a labeled, no-context answer when retrieval found nothing (skill note).

    Uses ``HYBRID_SYSTEM_PROMPT`` instead of the grounded ``SYSTEM_PROMPT``: the
    model may draw on general insurance/actuarial knowledge, but is instructed
    to still refuse for anything company-specific, and every non-refusal
    answer gets ``HYBRID_DISCLAIMER`` appended deterministically so it's never
    mistaken for an answer sourced from company documents.
    """
    messages = build_hybrid_messages(query, history)
    async for chunk in _stream_chat(messages, _hybrid_disclaimer_suffix):
        yield chunk


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


def generate_plain(prompt: str) -> str:
    """Context-free passthrough for UI meta-tasks (chat title/tag generation).

    Open WebUI sends these through the same chat endpoint; they must NOT run
    the RAG pipeline (minutes of retrieval on CPU) nor see the grounded system
    prompt (whose refusal rule would turn every chat title into the refusal
    sentence). Returns "" on failure — Open WebUI then keeps its default title.
    """
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json=_ollama_payload([{"role": "user", "content": prompt}], stream=False),
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        return strip_think(resp.json().get("message", {}).get("content", ""))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Meta-task generation failed: %s", exc)
        return ""


def _generate_chat(
    messages: list[dict[str, str]], suffix_fn: Callable[[str], str]
) -> str:
    """Shared non-streaming Ollama call + deterministic suffix (mirrors ``_stream_chat``)."""
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json=_ollama_payload(messages, stream=False),
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        answer = strip_think(content)
        return answer + suffix_fn(answer)
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Generation failed: %s", exc)
        return _CONNECTION_ERROR_MESSAGE


def generate_answer(
    query: str,
    hits: list[Hit],
    history: list[ChatMessage] | None = None,
    advisory: bool = False,
) -> str:
    """Non-streaming variant: block for the full grounded answer (``stream: false``)."""
    messages = build_messages(query, hits, history, advisory=advisory)
    return _generate_chat(messages, _grounded_suffix_fn(hits, advisory))


def generate_hybrid_answer(query: str, history: list[ChatMessage] | None = None) -> str:
    """Non-streaming variant of ``stream_hybrid_answer`` (``stream: false``)."""
    messages = build_hybrid_messages(query, history)
    return _generate_chat(messages, _hybrid_disclaimer_suffix)
