"""Deterministic metric-type hints for table chunks (no LLM).

Bare ``%``-by-year Markdown tables look alike to dense/sparse retrieval whether
they are lãi suất cam kết tối thiểu or tỷ lệ bồi thường. Appending an explicit
Vietnamese label to ``embed_text`` (never ``display_text``) gives bge-m3 a
lexical signal so claim-% queries prefer the right schedule — and the
generation prompt can refuse remapping when the wrong type is all that remains.
"""

from __future__ import annotations

import re
import unicodedata

# Markdown table row (at least one pipe after stripping).
_TABLE_LINE_RE = re.compile(r"^\s*\|", re.MULTILINE)

# (folded needle, Vietnamese hint). Longer / more specific phrases first.
_HINTS: tuple[tuple[str, str], ...] = (
    (
        "lai suat cam ket",
        "bảng lãi suất cam kết tối thiểu (không phải tỷ lệ bồi thường)",
    ),
    (
        "lai suat toi thieu",
        "bảng lãi suất cam kết tối thiểu (không phải tỷ lệ bồi thường)",
    ),
    (
        "lai suat dam bao",
        "bảng lãi suất đảm bảo (không phải tỷ lệ bồi thường)",
    ),
    (
        "phi ban dau",
        "bảng / mục phí ban đầu (không phải tỷ lệ bồi thường)",
    ),
    (
        "phi quan ly quy",
        "bảng / mục phí quản lý quỹ (không phải tỷ lệ bồi thường)",
    ),
    (
        "phi quan ly hop dong",
        "bảng / mục phí quản lý hợp đồng (không phải tỷ lệ bồi thường)",
    ),
    ("ty le boi thuong", "bảng tỷ lệ bồi thường / quyền lợi"),
    ("so tien bao hiem", "bảng / mục số tiền bảo hiểm / quyền lợi"),
    ("quyen loi tu vong", "bảng / mục quyền lợi tử vong"),
)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def has_markdown_table(text: str) -> bool:
    """True when ``text`` contains at least one Markdown table row."""
    return bool(_TABLE_LINE_RE.search(text))


def metric_type_hint(text: str) -> str | None:
    """Return a short embed-only label for the metric in ``text``, if known.

    Scans caption + body (diacritic-folded). Returns ``None`` when there is no
    table or no recognized metric phrase — callers must not invent a type.
    """
    if not text or not has_markdown_table(text):
        return None
    folded = _fold(text)
    for needle, hint in _HINTS:
        if needle in folded:
            return hint
    return None
