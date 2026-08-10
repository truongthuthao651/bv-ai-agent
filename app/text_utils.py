"""Shared text-normalization helpers.

``fold_text`` is the diacritic-folded, lowercased form every deterministic
guard's substring matching runs on. Extracted from 5 byte-for-byte-identical
copies (MAINT1, 2026-08-05 audit) — a future correctness fix (e.g. a missed
character class) previously had to be applied 6 times with nothing enforcing
that it actually was. Not the same function as
``app.ingestion.parsers.markdown``'s word-level ``_fold`` (different
normalization order, different purpose — deliberately left separate).
"""

from __future__ import annotations

import unicodedata
import re


def fold_text(text: str) -> str:
    """Lowercase + strip Vietnamese diacritics (đ/Đ -> d) for substring matching."""
    text = unicodedata.normalize("NFC", text).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


# Common CJK tokens that leak from multilingual LLM weights into Vietnamese answers.
_CJK_REPLACEMENTS: dict[str, str] = {
    "投保": " tham gia",
    "被保险人": " người được bảo hiểm",
    "投保人": " người mua bảo hiểm",
}

_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def sanitize_model_output(text: str, *, strip_edges: bool = False) -> str:
    """Fix stray CJK characters in otherwise Vietnamese assistant answers.

    ``strip_edges`` must stay False when sanitizing individual stream tokens —
    leading spaces are often the only separator between the previous token and
    the next word; stripping them glues words together ("Phí" + " thuần" →
    "Phíthuần"). Call with ``strip_edges=True`` only on a complete answer.
    """
    if not text:
        return text
    for src, dst in _CJK_REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = _CJK_RUN.sub("", text)
    text = re.sub(r" +", " ", text)
    return text.strip() if strip_edges else text
