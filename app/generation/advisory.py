"""Deterministic detector for advisory / synthesis questions.

Company documents state *facts* ("quyền lợi tử vong: 100% Số tiền bảo hiểm").
They never state a *conclusion about the facts* — "which of these two products
should the customer pick?", "what's the difference?", "which is better for a
young customer?". Under the strict system prompt a small local model reads rule
3 ("nếu ngữ cảnh không đủ thông tin ... PHẢI trả lời: Tôi không tìm thấy thông
tin trong tài liệu") and refuses those outright, even in the very next turn
after it has just produced a full comparison table from the same documents.
(Observed: "lập bảng so sánh quyền lợi A và B" answered in full, then "KH sẽ
chọn sản phẩm nào nhỉ" refused.)

This module classifies such a turn so the chat endpoint can route it to
``ADVISORY_SYSTEM_PROMPT``, which keeps every datum sourced from the retrieved
context but permits comparing across them and phrasing conditional
recommendations.

Deliberately deterministic (regex over folded Vietnamese text, no LLM call):
the classification runs on every turn and must not add latency, and a
misfire must be inspectable. Diacritic-folded so habitual no-diacritics typing
("nen chon san pham nao") classifies the same as fully-typed Vietnamese.

Note this only widens *reasoning*, never sourcing: the advisory prompt still
refuses on an absent product, and the product-scope / metric guards run before
routing either way.
"""

from __future__ import annotations

import re

from app.retrieval.product_scope import _fold

# Phrases that ask for a judgement/recommendation rather than a lookup. Matched
# against the diacritic-folded query, so each pattern is written folded.
_ADVISORY_PATTERNS: tuple[str, ...] = (
    # choosing between options
    r"\bnen\s+(chon|mua|tu\s*van|lay|dung)\b",
    r"\bchon\s+(san\s*pham|goi|cai|loai|hop\s*dong)?\s*nao\b",
    r"\bsan\s*pham\s+nao\b",
    r"\bcai\s+nao\b",
    r"\bloai\s+nao\b",
    r"\bben\s+nao\b",
    r"\bphuong\s*an\s+nao\b",
    # suitability
    r"\bphu\s*hop\b",
    r"\bthich\s*hop\b",
    r"\bdanh\s*cho\s+ai\b",
    r"\bai\s+nen\b",
    # explicit advice
    r"\btu\s*van\b",
    r"\bkhuyen\b",
    r"\bloi\s*khuyen\b",
    r"\bgoi\s*y\b",
    r"\bdanh\s*gia\b",
    r"\bnhan\s*xet\b",
    # comparison / trade-off framing
    r"\bso\s*sanh\b",
    r"\bkhac\s*(nhau|biet)\b",
    r"\buu\s*(diem|the)\b",
    r"\bnhuoc\s*diem\b",
    r"\bhan\s*che\s+(cua|gi)\b",
    r"\bloi\s*the\b",
    r"\bhon\s+kem\b",
    r"\btot\s*hon\b",
    r"\bloi\s+hon\b",
    r"\bhon\s+han\b",
    # "vì sao / tại sao nên"
    r"\b(vi\s*sao|tai\s*sao)\b.{0,20}\bnen\b",
)

_ADVISORY_RE = re.compile("|".join(_ADVISORY_PATTERNS))

# Comparison alone is not advisory when the user asked for a plain extraction
# ("liệt kê", "trích", "bảng"): those are answerable verbatim from context and
# the strict prompt already handles them well. Only suppress when NO stronger
# advisory cue is present — "lập bảng so sánh rồi nên chọn cái nào" stays
# advisory.
_LOOKUP_ONLY_RE = re.compile(r"\b(liet\s*ke|trich\s*(dan|xuat)|tra\s*cuu)\b")

# Cues strong enough to keep advisory mode even alongside a lookup verb.
_STRONG_RE = re.compile(
    r"\bnen\s+(chon|mua|tu\s*van|lay|dung)\b|\bsan\s*pham\s+nao\b|\btu\s*van\b"
    r"|\bkhuyen\b|\bphu\s*hop\b|\bcai\s+nao\b|\bchon\s+.{0,12}nao\b"
)


def is_advisory_query(query: str) -> bool:
    """True when the turn asks for comparison/recommendation, not a lookup.

    Pure and offline; safe to call on every request.
    """
    if not query or not query.strip():
        return False
    folded = _fold(query)
    if not _ADVISORY_RE.search(folded):
        return False
    if _LOOKUP_ONLY_RE.search(folded) and not _STRONG_RE.search(folded):
        return False
    return True
