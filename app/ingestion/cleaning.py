"""Text cleaning: Unicode normalization and header/footer stripping.

Small pure functions so they're unit-testable without external services. All Vietnamese
text is NFC-normalized at ingestion (CLAUDE.md convention).
"""

from __future__ import annotations

import re
import unicodedata

# Lines that are just a page number ("- 12 -", "Trang 3", "3/10") are boilerplate.
_PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:-+\s*)?(?:trang\s+)?\d+(?:\s*/\s*\d+)?\s*(?:-+)?\s*$",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """NFC-normalize and tidy whitespace without touching content.

    - Unicode NFC (composes Vietnamese diacritics into canonical form).
    - Normalize CRLF/CR to LF.
    - Strip trailing spaces per line; collapse 3+ blank lines to a single blank.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def strip_headers_footers(text: str, *, repeated_min: int = 3) -> str:
    """Remove page-number lines and running headers/footers.

    A "running" header/footer is a short line that repeats across many pages;
    we drop non-heading lines that occur at least ``repeated_min`` times. Markdown
    headings (``#``) and table rows (``|``) are never removed.
    """
    lines = text.split("\n")

    counts: dict[str, int] = {}
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "|", "$")):
            counts[stripped] = counts.get(stripped, 0) + 1

    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _PAGE_NUMBER_RE.match(stripped):
            continue
        if (
            stripped
            and not stripped.startswith(("#", "|", "$"))
            and len(stripped) < 60
            and counts.get(stripped, 0) >= repeated_min
        ):
            continue
        kept.append(line)

    return "\n".join(kept)
