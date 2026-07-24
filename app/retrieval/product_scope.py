"""Deterministic product-scope guard.

Retrieval has no product filter, so a query naming a *specific* product that is
NOT in the corpus can still return semantically-similar chunks from a DIFFERENT
product — life-insurance benefit clauses ("quyền lợi tử vong", "quyền lợi đáo
hạn", ...) are near-identical across products, so the reranker keeps them above
its floor and the model then answers, citing the wrong product. (Observed:
asking about "An Thịnh Phúc Niên", which had been deleted, produced an answer
sourced from "An Khang Như Ý".)

This module detects that case from the query text plus the titles of the
retrieved documents, so the chat endpoint can refuse deterministically instead
of answering from the wrong product — the same guardrail pattern used for the
calc/hybrid disclaimers (a small local model can't be trusted to notice the
mismatch on its own).

How it works: it isolates the product-name phrase that follows a product cue
("bảo hiểm ...", "sản phẩm ...") in the query, then checks whether any of that
phrase's distinctive tokens appears in *any* retrieved document title. If none
do, the named product is absent from what was retrieved → refuse. Matching is
diacritic-folded so habitual no-diacritics typing ("an thinh phuc nien") still
lines up with a diacritic title.

Note: a present product whose title is a bare abbreviation (e.g. "BHLKC_AKNY")
carries none of the product-name tokens, so this guard will (correctly, per the
existing doc-title/retrieval guidance) refuse until the document is re-ingested
with a "Tên tài liệu" that spells the product name out — turning a silent
wrong-product answer into a loud, actionable refusal.

Pure and offline — unit-tested without Qdrant or an LLM.
"""

from __future__ import annotations

import re
import unicodedata

# Product cue phrases (diacritic-folded); the product name is whatever noun
# phrase follows one of these in the query.
_TRIGGERS: tuple[tuple[str, ...], ...] = (
    ("bao", "hiem"),
    ("san", "pham"),
    ("hop", "dong"),
    ("chuong", "trinh"),
    ("goi",),
)

# Generic tokens (diacritic-folded) that are NEVER part of a distinctive product
# name: insurance product-type connectors ("liên kết chung", "hỗn hợp", "nhân
# thọ"...) plus question/filler/verb words. Used both to skip leading connectors
# right after a trigger and to terminate the product-name span.
_GENERIC: frozenset[str] = frozenset(
    {
        # insurance-generic nouns / product-type connectors
        "bao",
        "hiem",
        "san",
        "pham",
        "goi",
        "chuong",
        "trinh",
        "hop",
        "dong",
        "lien",
        "ket",
        "chung",
        "hon",
        "nhan",
        "tho",
        "tu",
        "ky",
        "tron",
        "doi",
        "an",
        "loai",
        "gom",
        "bao_gom",
        # question / filler / verb words
        "la",
        "gi",
        "co",
        "cua",
        "cho",
        "ve",
        "nhu",
        "the",
        "nao",
        "nhieu",
        "liet",
        "ke",
        "chi",
        "tiet",
        "quyen",
        "loi",
        "cac",
        "va",
        "nhung",
        "mot",
        "voi",
        "duoc",
        "hay",
        "can",
        "muon",
        "xin",
        "hoi",
        "thong",
        "tin",
        "den",
        "tai",
        "theo",
        "khi",
        "cung",
        "hoac",
        "danh",
        "sach",
        "toi",
        "ban",
        "minh",
        "biet",
        "giup",
        "gium",
        "xem",
        "tra",
        "cuu",
        "nay",
        "do",
        "kia",
        "tat",
        "ca",
        "nhe",
        "a",
        "voi_lai",
    }
)

# Generics that can sit *inside* a product name between distinctive tokens
# ("An Khang Như Ý") without ending the span. "và" stays a hard terminator so
# "A và B" still yields two separate products.
_NAME_BRIDGES: frozenset[str] = frozenset({"nhu"})

# The company's OWN name is not a product name. "sản phẩm bảo hiểm của Bảo Việt
# Life" used to yield the span ["viet", "life"], which no document title covers,
# so the guard refused a perfectly answerable question. Longest phrase first so
# "bảo việt life" is consumed whole rather than leaving a stray "life".
_COMPANY_SELF_PHRASES: tuple[tuple[str, ...], ...] = (
    ("bao", "viet", "nhan", "tho"),
    ("bao", "viet", "life"),
    ("bao", "viet"),
    ("bvl",),
)

# Tokens that end the skip-over-connectors scan after a cue phrase. Without
# them, "sản phẩm bảo hiểm của X và các công ty khác" skips right across the
# clause boundary and collects whatever noun follows as a "product name".
_HARD_SEPARATORS: frozenset[str] = frozenset({"va", "hoac", "hay"})


def _strip_company_self_reference(tokens: list[str]) -> list[str]:
    """Drop mentions of our own company so they can't be read as a product."""
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        for phrase in _COMPANY_SELF_PHRASES:
            if tuple(tokens[i : i + len(phrase)]) == phrase:
                i += len(phrase)
                break
        else:
            out.append(tokens[i])
            i += 1
    return out


def _fold(text: str) -> str:
    """Lowercase + strip Vietnamese diacritics (so no-diacritics typing matches)."""
    text = unicodedata.normalize("NFC", text).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _fold_tokens(text: str) -> list[str]:
    """Diacritic-folded word tokens of ``text`` (Unicode-aware, punctuation dropped)."""
    return re.findall(r"\w+", _fold(text), flags=re.UNICODE)


def _collect_name_run(tokens: list[str], start: int) -> tuple[list[str], int]:
    """Collect distinctive name tokens from ``start``, allowing ``_NAME_BRIDGES``.

    Returns ``(span, index_after_run)``. Bridge tokens are skipped (not added to
    the distinctive span) so "khang nhu y" → ``["khang", "y"]``.
    """
    span: list[str] = []
    j = start
    n = len(tokens)
    while j < n:
        tok = tokens[j]
        if tok not in _GENERIC:
            span.append(tok)
            j += 1
            continue
        if (
            tok in _NAME_BRIDGES
            and span
            and j + 1 < n
            and tokens[j + 1] not in _GENERIC
        ):
            j += 1  # skip bridge, keep collecting
            continue
        break
    return span, j


def _product_spans(tokens: list[str]) -> list[list[str]]:
    """All distinctive product-name spans in order of appearance (deduped).

    Scans for a trigger (``bảo hiểm`` ...), skips the generic connectors right
    after it (``liên kết chung``, ``an`` ...), then collects the name run.
    Comparison questions ("A và B") yield one span per product.

    Our own company name is removed first (it is not a product), and the
    connector skip stops at a clause boundary so a cue phrase cannot reach
    across "và" and claim an unrelated noun as a product name.
    """
    tokens = _strip_company_self_reference(tokens)
    n = len(tokens)
    spans: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    i = 0
    while i < n:
        matched = 0
        for trig in _TRIGGERS:
            if tuple(tokens[i : i + len(trig)]) == trig:
                matched = len(trig)
                break
        if not matched:
            i += 1
            continue
        j = i + matched
        while j < n and tokens[j] in _GENERIC:  # skip leading connectors
            if tokens[j] in _HARD_SEPARATORS:  # never cross a clause boundary
                break
            j += 1
        span, j = _collect_name_run(tokens, j)
        key = tuple(span)
        if span and key not in seen:
            seen.add(key)
            spans.append(span)
        i = max(j, i + 1)
    return spans


def _product_span(tokens: list[str]) -> list[str]:
    """Longest distinctive product-name span, or [].

    Kept for sticky single-product conversation scope; comparison retrieval uses
    ``_product_spans`` / ``named_product_labels`` instead.
    """
    spans = _product_spans(tokens)
    if not spans:
        return []
    return max(spans, key=len)


def named_product_labels(
    query: str, *, titles: list[str] | None = None
) -> list[str]:
    """Surface-form product labels named in ``query``, in appearance order.

    Prefers full indexed document titles when the query mentions them (even
    without a ``bảo hiểm`` cue — e.g. "an khang như ý và an lộc vững bền").
    Falls back to cue-phrase spans from the query text.
    """
    if not query.strip():
        return []

    known_titles = titles if titles is not None else _load_indexed_titles()
    from_titles = mentioned_doc_titles(query, known_titles)
    if len(from_titles) >= 2:
        return from_titles

    folded = _fold_tokens(query)
    spans = _product_spans(folded)
    if not spans:
        return from_titles

    raw_words = re.findall(r"\w+", query, flags=re.UNICODE)
    labels: list[str] = []
    used_starts: set[int] = set()
    for span in spans:
        label: str | None = None
        for i in range(len(folded) - len(span) + 1):
            if i in used_starts:
                continue
            if _span_matches_at(folded, i, span):
                end = _span_end_index(folded, i, span)
                if len(raw_words) == len(folded):
                    label = " ".join(raw_words[i:end])
                else:
                    label = " ".join(span)
                used_starts.add(i)
                break
        labels.append(label or " ".join(span))

    # Cue spans win when they found more products than title matching
    # (title matching can miss short suffixes like "Ý").
    if len(labels) >= 2:
        return labels
    return from_titles or labels


def _span_matches_at(tokens: list[str], start: int, span: list[str]) -> bool:
    """True when ``span``'s distinctive tokens appear in order from ``start``."""
    k = 0
    j = start
    while j < len(tokens) and k < len(span):
        if tokens[j] == span[k]:
            k += 1
            j += 1
        elif tokens[j] in _NAME_BRIDGES and k > 0:
            j += 1
        else:
            return False
    return k == len(span)


def _span_end_index(tokens: list[str], start: int, span: list[str]) -> int:
    """Index just past the last token of ``span`` aligned at ``start``."""
    k = 0
    j = start
    while j < len(tokens) and k < len(span):
        if tokens[j] == span[k]:
            k += 1
            j += 1
        elif tokens[j] in _NAME_BRIDGES and k > 0:
            j += 1
        else:
            break
    return j


def title_covers_product(title: str, product_label: str) -> bool:
    """True when ``title`` shares a distinctive token with ``product_label``."""
    label_toks = _distinctive_title_tokens(product_label)
    if not label_toks:
        return False
    title_toks = set(_fold_tokens(title))
    return bool(label_toks & title_toks)


def _distinctive_title_tokens(title: str) -> set[str]:
    """Non-generic tokens that identify a document title.

    Keeps single-character tokens (e.g. ``ý``/``y`` in "An Khang Như Ý") —
    dropping them left some real product titles with only one usable token
    and made informal nickname matching fail.
    """
    return {t for t in _fold_tokens(title) if t not in _GENERIC}


def mentioned_doc_titles(query: str, titles: list[str]) -> list[str]:
    """Indexed doc titles whose distinctive name tokens appear in ``query``.

    Catches informal mentions that omit the ``bảo hiểm`` / ``sản phẩm`` cue
    ("so sánh an khang như ý và an lộc vững bền"). Requires ≥2 distinctive
    token overlaps so a lone shared word cannot claim a title. Ordered by the
    earliest distinctive-token position in the query.
    """
    if not query.strip() or not titles:
        return []
    q_toks = _fold_tokens(query)
    q_set = set(q_toks)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for title in titles:
        dist = _distinctive_title_tokens(title)
        if len(dist) < 2:
            continue
        needed = max(2, (len(dist) + 1) // 2)
        overlap = dist & q_set
        if len(overlap) < needed:
            continue
        key = title.casefold()
        if key in seen:
            continue
        positions = [i for i, t in enumerate(q_toks) if t in overlap]
        pos = min(positions) if positions else 0
        seen.add(key)
        scored.append((pos, title))
    scored.sort(key=lambda item: item[0])
    return [title for _, title in scored]


def _load_indexed_titles() -> list[str]:
    """Best-effort titles from Qdrant; empty when the store is unavailable."""
    try:
        from app.ingestion import indexer

        return [d.doc_title for d in indexer.list_documents()]
    except Exception:  # pragma: no cover - Qdrant locked/offline
        return []


def query_names_absent_product(query: str, hit_titles: list[str]) -> bool:
    """True when every product named in the query is absent from hit titles.

    Only fires when the query explicitly names at least one product via a cue
    phrase (``bảo hiểm …``); informal nickname-only questions are handled by
    comparison title matching instead and are never blocked here. For
    comparisons naming A and B, refuse only when *neither* appears in any
    retrieved title.
    """
    spans = _product_spans(_fold_tokens(query))
    if not spans:
        return False
    title_tokens: set[str] = set()
    for title in hit_titles:
        title_tokens.update(_fold_tokens(title))
    return all(not (set(span) & title_tokens) for span in spans)
