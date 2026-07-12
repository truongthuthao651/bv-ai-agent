"""Standalone-question rewriting from chat history.

A follow-up like "còn phí gộp thì sao?" only makes sense with the preceding
turns. Before retrieval, the local LLM rewrites it into a standalone question
("Phí gộp của sản phẩm An Tâm Bảo Vệ là gì?") so hybrid search has real lexical
content to match against. Gated by ``settings.enable_query_rewrite`` and
skipped entirely when there's no history (skill, section 5).

The Ollama call is injectable so tests exercise the gating/formatting logic
without a running model.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from app.config.settings import settings
from app.models.schemas import ChatMessage

logger = logging.getLogger(__name__)

Rewriter = Callable[[str], str]

# Only the last few turns matter for disambiguating a follow-up; keeps the
# prompt short for the small local model.
_MAX_HISTORY_TURNS = 6

_REWRITE_PROMPT = (
    "Dựa trên lịch sử hội thoại dưới đây, hãy viết lại câu hỏi cuối cùng của "
    "người dùng thành một câu hỏi độc lập, đầy đủ ngữ cảnh, bằng tiếng Việt. "
    "Chỉ trả về câu hỏi đã viết lại, không thêm lời dẫn hay giải thích.\n\n"
    "Lịch sử hội thoại:\n{history}\n\n"
    "Câu hỏi cuối cùng: {query}"
)


def _format_history(history: list[ChatMessage]) -> str:
    return "\n".join(f"{m.role}: {m.content}" for m in history[-_MAX_HISTORY_TURNS:])


def _ollama_rewrite(prompt: str) -> str:
    """Ask the local LLM to rewrite the prompt into a standalone question."""
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.chat_model,
                "prompt": prompt,
                "stream": False,
                "think": False,  # qwen3: skip chain-of-thought for this fast utility call
                "keep_alive": settings.ollama_keep_alive,
                "options": {"temperature": 0.0},
            },
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Query rewrite failed, falling back to original query: %s", exc)
        return ""


def rewrite_standalone(
    history: list[ChatMessage],
    query: str,
    *,
    enabled: bool | None = None,
    rewrite: Rewriter | None = None,
) -> str:
    """Rewrite ``query`` into a standalone question using ``history``.

    Returns ``query`` unchanged when rewriting is disabled, there's no history
    (nothing to disambiguate), or the LLM call fails.
    """
    if enabled is None:
        enabled = settings.enable_query_rewrite
    if not enabled or not history:
        return query

    rewrite = rewrite or _ollama_rewrite
    prompt = _REWRITE_PROMPT.format(history=_format_history(history), query=query)
    rewritten = rewrite(prompt)
    return rewritten or query
