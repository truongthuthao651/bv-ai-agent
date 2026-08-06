"""Standalone-question rewriting from chat history.

A follow-up like "còn phí gộp thì sao?" only makes sense with the preceding
turns. Before retrieval, the local LLM rewrites it into a standalone question
("Phí gộp của sản phẩm An Tâm Bảo Vệ là gì?") so hybrid search has real lexical
content to match against. Gated by ``settings.enable_query_rewrite`` and
skipped entirely when there's no history (skill, section 5).

When a sticky product/document scope is known (from prior citations or user
turns), it is passed into the rewrite prompt and used as a deterministic
fallback if the small local model drops the name — see
``app.retrieval.conversation_scope``.

The Ollama call is injectable so tests exercise the gating/formatting logic
without a running model.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from app.config.settings import settings
from app.models.schemas import ChatMessage
from app.retrieval.conversation_scope import (
    cited_doc_titles,
    ensure_prior_topic,
    ensure_scope,
)

logger = logging.getLogger(__name__)

Rewriter = Callable[[str], str]

# Only the last few turns matter for disambiguating a follow-up; keeps the
# prompt short for the small local model.
_MAX_HISTORY_TURNS = 6

# Assistant answers (with full sources) drown the product name; keep a short
# preview plus any cited document titles for the rewriter.
_ASSISTANT_PREVIEW_CHARS = 240

_REWRITE_PROMPT = (
    "Dựa trên lịch sử hội thoại dưới đây, hãy viết lại câu hỏi cuối cùng của "
    "người dùng thành một câu hỏi độc lập, đầy đủ ngữ cảnh, bằng tiếng Việt. "
    "BẮT BUỘC giữ nguyên: (1) tên sản phẩm / tên tài liệu đang thảo luận, và "
    "(2) tình huống / chi tiết cụ thể ở câu hỏi trước (ví dụ hoạt động rủi ro, "
    "đối tượng KH, điều kiện claim) nếu câu hỏi cuối cùng vẫn tiếp nối cùng "
    "tình huống đó — kể cả khi người dùng không nhắc lại.\n"
    "Ví dụ: câu trước là «KH đi trượt tuyết và lặn biển claim QL thương tật?» "
    "rồi hỏi «thế tử vong thì sao» → viết lại thành «KH đi trượt tuyết và lặn "
    "biển claim quyền lợi tử vong có được không?».\n"
    "Chỉ trả về câu hỏi đã viết lại, không thêm lời dẫn hay giải thích.\n\n"
    "{scope_line}"
    "Lịch sử hội thoại:\n{history}\n\n"
    "Câu hỏi cuối cùng: {query}"
)


def _condense_assistant(content: str) -> str:
    """Shorten an assistant turn for the rewrite prompt without losing titles."""
    titles = cited_doc_titles(content)
    # Drop the deterministic sources footer before previewing — it is long and
    # the titles are re-attached explicitly below.
    body = content
    marker = "**Nguồn tham khảo:**"
    if marker in body:
        body = body.split(marker, 1)[0].rstrip()
    preview = body[:_ASSISTANT_PREVIEW_CHARS].rsplit("\n", 1)[0].strip()
    if len(body) > _ASSISTANT_PREVIEW_CHARS:
        preview = preview.rstrip() + "…"
    if titles:
        # Deduplicate, preserve order.
        seen: set[str] = set()
        ordered: list[str] = []
        for t in titles:
            if t not in seen:
                seen.add(t)
                ordered.append(t)
        cited = ", ".join(ordered[:5])
        return f"{preview}\n[Tài liệu đã trích dẫn: {cited}]".strip()
    return preview or body[:_ASSISTANT_PREVIEW_CHARS]


def _format_history(history: list[ChatMessage]) -> str:
    lines: list[str] = []
    for m in history[-_MAX_HISTORY_TURNS:]:
        content = _condense_assistant(m.content) if m.role == "assistant" else m.content
        lines.append(f"{m.role}: {content}")
    return "\n".join(lines)


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
                # num_ctx MUST match generator._ollama_payload's: this call
                # runs on EVERY turn, immediately before generation on the
                # same loaded llama.cpp instance. A mismatched context size
                # forces a full model reload for the size change, not a
                # no-op — found live, 2026-08-06, via
                # ~/.ollama/logs/server.log showing n_ctx_slot flip-flopping
                # between requests and correlating with intermittent Ollama
                # 500s. Since this runs before generation on every request,
                # it was the single biggest unnecessary latency cost in the
                # whole pipeline, not just an eval-time issue.
                "options": {
                    "temperature": 0.0,
                    "num_ctx": settings.llm_context_window,
                },
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
    scope: str | None = None,
    enabled: bool | None = None,
    rewrite: Rewriter | None = None,
) -> str:
    """Rewrite ``query`` into a standalone question using ``history``.

    Returns ``query`` unchanged when rewriting is disabled, there's no history
    (nothing to disambiguate), or the LLM call fails. Always applies
    ``ensure_prior_topic`` (carry scenario details from the previous user turn)
    and, when ``scope`` is set, ``ensure_scope`` (restore a dropped product/
    document name) as deterministic safety nets after the LLM rewrite.
    """
    if enabled is None:
        enabled = settings.enable_query_rewrite

    rewritten = query
    if enabled and history:
        rewrite = rewrite or _ollama_rewrite
        scope_line = (
            f"Tài liệu/sản phẩm đang được thảo luận: {scope}\n\n" if scope else ""
        )
        prompt = _REWRITE_PROMPT.format(
            scope_line=scope_line,
            history=_format_history(history),
            query=query,
        )
        llm_out = rewrite(prompt)
        if llm_out:
            rewritten = llm_out

    if history:
        rewritten = ensure_prior_topic(rewritten, history)
    if scope:
        rewritten = ensure_scope(rewritten, scope)
    return rewritten
