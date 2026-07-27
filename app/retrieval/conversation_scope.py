"""Sticky product/document/topic scope across chat turns.

Retrieval is stateless per turn: a follow-up like "thế tử vong thì sao?" has
no lexical signal for the prior scenario ("đi trượt tuyết và lặn biển… claim
QL thương tật"), so hybrid search can pull an unrelated exclusion clause —
or the wrong product entirely.

This module recovers:
1. The active product/document (last-cited ``Nguồn tham khảo`` title, else a
   product phrase from prior user turns) via ``ensure_scope``.
2. The prior user question's topical content when the new turn is a short
   continuation, via ``ensure_prior_topic``.

Both are deterministic (no LLM) and run after standalone-question rewrite as
safety nets when the small local model drops context.
"""

from __future__ import annotations

import re
from collections import Counter

from app.models.schemas import ChatMessage
from app.retrieval.product_scope import _GENERIC, _fold_tokens, _product_span

# Matches one line of the deterministic sources footer from format_sources:
#   - [1] [Bảo hiểm liên kết chung An Khang Như Ý](http://...) — Điều 5
_SOURCE_TITLE_RE = re.compile(
    r"^\s*-\s*\[\d+\]\s*\[([^\]]+)\]\([^)]*\)",
    re.MULTILINE,
)

# Injection markers we may have appended on an earlier turn — strip before reuse.
_INJECTION_RE = re.compile(
    r"\s*\((?:tài liệu|ngữ cảnh câu trước):\s*[^)]+\)\s*$",
    re.IGNORECASE,
)

_FOLLOWUP_START = re.compile(
    r"^\s*(thế|thế còn|còn|vậy|vậy còn|còn về|thế còn về)\b",
    re.IGNORECASE | re.UNICODE,
)
_FOLLOWUP_END = re.compile(
    r"\b(thì sao|thế nào|như thế nào|sao)\s*\??\s*$",
    re.IGNORECASE | re.UNICODE,
)

# How far back to look for a sticky label (same window as rewrite/generation).
_MAX_HISTORY_TURNS = 6

# A rewritten follow-up that already keeps this fraction of the prior question's
# distinctive tokens is considered complete — no topic injection needed.
_PRIOR_TOPIC_COVER_RATIO = 0.5


def cited_doc_titles(assistant_content: str) -> list[str]:
    """Document titles listed in an assistant ``Nguồn tham khảo`` block."""
    return [m.group(1).strip() for m in _SOURCE_TITLE_RE.finditer(assistant_content)]


def _strip_injections(text: str) -> str:
    """Remove trailing ``(tài liệu: …)`` / ``(ngữ cảnh câu trước: …)`` suffixes."""
    out = text.rstrip()
    while True:
        cleaned = _INJECTION_RE.sub("", out).rstrip()
        if cleaned == out:
            return out
        out = cleaned


def _distinctive(text: str) -> set[str]:
    """Folded tokens that can identify a product/title/topic (generics stripped)."""
    return {t for t in _fold_tokens(text) if t not in _GENERIC and len(t) > 1}


def query_covers_scope(query: str, scope: str) -> bool:
    """True when ``query`` already carries enough of ``scope`` to retrieve it."""
    scope_toks = _distinctive(scope)
    if not scope_toks:
        return True
    query_toks = _distinctive(query)
    # Majority overlap: short titles need most tokens; long titles tolerate a miss.
    needed = max(1, (len(scope_toks) + 1) // 2)
    return len(scope_toks & query_toks) >= needed


def _scope_from_citations(history: list[ChatMessage]) -> str | None:
    """Most-cited document title in the newest assistant turn that has sources."""
    for msg in reversed(history[-_MAX_HISTORY_TURNS:]):
        if msg.role != "assistant":
            continue
        titles = cited_doc_titles(msg.content)
        if not titles:
            continue
        # Prefer the mode (same product cited many times); tie → first listed.
        counts = Counter(titles)
        return counts.most_common(1)[0][0]
    return None


def _scope_from_user_turns(history: list[ChatMessage]) -> str | None:
    """Best-effort product phrase from recent user messages (pre-citation turns)."""
    # Walk newest-first so the latest named product wins.
    for msg in reversed(history[-_MAX_HISTORY_TURNS:]):
        if msg.role != "user":
            continue
        tokens = _fold_tokens(msg.content)
        span = _product_span(tokens)
        if not span:
            continue
        # Recover the original surface form: locate the span in the folded
        # token list and slice the matching words from the raw message.
        folded_msg = _fold_tokens(msg.content)
        # Find where the span starts in the full token list.
        for i in range(len(folded_msg) - len(span) + 1):
            if folded_msg[i : i + len(span)] == span:
                raw_words = re.findall(r"\w+", msg.content, flags=re.UNICODE)
                if len(raw_words) == len(folded_msg):
                    return " ".join(raw_words[i : i + len(span)])
                return " ".join(span)
        return " ".join(span)
    return None


def active_scope(history: list[ChatMessage]) -> str | None:
    """Sticky product/document label for this conversation, or ``None``."""
    if not history:
        return None
    return _scope_from_citations(history) or _scope_from_user_turns(history)


def cited_titles_in_history(history: list[ChatMessage]) -> list[str]:
    """Distinct document titles cited by recent assistant turns, newest first.

    ``active_scope`` collapses a conversation to ONE product, which is right for
    a scoped follow-up but wrong for an advisory follow-up continuing a
    comparison: "KH sẽ chọn sản phẩm nào nhỉ" names no product, so single-scope
    retrieval pins one of the two and the other product's benefits never reach
    the context. This returns every product still on the table so the comparison
    retrieval path can give each one its own quota.
    """
    out: list[str] = []
    seen: set[str] = set()
    for msg in reversed(history[-_MAX_HISTORY_TURNS:]):
        if msg.role != "assistant":
            continue
        for title in cited_doc_titles(msg.content):
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(title)
    return out


def last_user_question(history: list[ChatMessage]) -> str | None:
    """Most recent user turn in ``history``, with any prior injections stripped."""
    for msg in reversed(history[-_MAX_HISTORY_TURNS:]):
        if msg.role == "user" and msg.content.strip():
            return _strip_injections(msg.content)
    return None


def looks_like_followup(query: str) -> bool:
    """True for short continuations ("thế … thì sao", "còn …", bare fragments)."""
    bare = _strip_injections(query).strip()
    if not bare:
        return False
    words = _fold_tokens(bare)
    if _FOLLOWUP_START.search(bare) or _FOLLOWUP_END.search(bare):
        return len(words) <= 16
    return len(words) <= 6


def ensure_prior_topic(query: str, history: list[ChatMessage]) -> str:
    """Reattach the previous user question when a short follow-up dropped its topic.

    Example: prior "KH đi trượt tuyết và lặn biển… claim QL thương tật?", follow-up
    "thế tử vong thì sao" → append ``(ngữ cảnh câu trước: …)`` so retrieval still
    sees skiing/diving. No-op when the rewrite already kept enough prior tokens,
    or the new turn does not look like a continuation.
    """
    prior = last_user_question(history)
    if not prior or not query.strip():
        return query
    bare = _strip_injections(query)
    if not looks_like_followup(bare):
        return query

    prior_toks = _distinctive(prior)
    if not prior_toks:
        return query
    covered = len(prior_toks & _distinctive(bare)) / len(prior_toks)
    if covered >= _PRIOR_TOPIC_COVER_RATIO:
        return query

    # Keep any injection already on ``query`` (e.g. tài liệu) after the bare text.
    suffix = query[len(bare) :] if query.startswith(bare) else ""
    return f"{bare.rstrip()} (ngữ cảnh câu trước: {prior.strip()}){suffix}"


def ensure_scope(query: str, scope: str | None) -> str:
    """Append ``scope`` to ``query`` when the follow-up dropped the product name.

    No-op when scope is absent, already covered, or the query names a
    *different* product (user switched topic — don't drag the old title along).
    """
    if not scope or not query.strip():
        return query
    if query_covers_scope(query, scope):
        return query

    query_product = set(_product_span(_fold_tokens(query)))
    scope_toks = _distinctive(scope)
    if query_product and scope_toks and not (query_product & scope_toks):
        return query

    return f"{query.rstrip()} (tài liệu: {scope})"
