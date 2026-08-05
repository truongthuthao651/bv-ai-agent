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


def fold_text(text: str) -> str:
    """Lowercase + strip Vietnamese diacritics (đ/Đ -> d) for substring matching."""
    text = unicodedata.normalize("NFC", text).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if not unicodedata.combining(c))
