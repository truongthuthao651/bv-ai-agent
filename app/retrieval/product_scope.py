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


def _fold(text: str) -> str:
    """Lowercase + strip Vietnamese diacritics (so no-diacritics typing matches)."""
    text = unicodedata.normalize("NFC", text).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _fold_tokens(text: str) -> list[str]:
    """Diacritic-folded word tokens of ``text`` (Unicode-aware, punctuation dropped)."""
    return re.findall(r"\w+", _fold(text), flags=re.UNICODE)


def _product_span(tokens: list[str]) -> list[str]:
    """Distinctive product-name tokens following a product cue, or [].

    Scans for a trigger (``bảo hiểm`` ...), skips the generic connectors right
    after it (``liên kết chung``, ``an`` ...), then collects the contiguous run
    of non-generic tokens up to the next generic/question word — that run is the
    product name. Returns the longest such span across all triggers.
    """
    n = len(tokens)
    best: list[str] = []
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
            j += 1
        span: list[str] = []
        while j < n and tokens[j] not in _GENERIC:  # collect the name run
            span.append(tokens[j])
            j += 1
        if len(span) > len(best):
            best = span
        i = max(j, i + 1)
    return best


def query_names_absent_product(query: str, hit_titles: list[str]) -> bool:
    """True when the query names a product that no retrieved title covers.

    Only fires when the query explicitly names a product (via a cue phrase);
    plain topical questions ("bảo hiểm nhân thọ là gì") yield no span and are
    never blocked. The named product is considered present when any of its
    distinctive tokens appears in any retrieved document title.
    """
    span = set(_product_span(_fold_tokens(query)))
    if not span:
        return False
    title_tokens: set[str] = set()
    for title in hit_titles:
        title_tokens.update(_fold_tokens(title))
    return not (span & title_tokens)
