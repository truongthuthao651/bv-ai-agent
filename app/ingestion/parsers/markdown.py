"""Markdown -> ParsedSection sectionizer (shared helper).

Markdown+LaTeX is the canonical format, so this is the common back-end for both
the DOCX parser (pandoc emits Markdown) and direct ``.md`` ingestion. It splits
on ATX headings and builds a ``section_path`` from the heading stack, recognizing
the Vietnamese legal hierarchy (Chương/Mục/Điều/Khoản/Điểm) embedded in heading
text so paths read like "Chương II > Điều 5".

This is a structural split only — token-budget chunking happens later in
chunking.py. Pure function; unit-testable without Docker.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

from app.models.schemas import ParsedSection


class TitleResult(NamedTuple):
    """A derived document title plus how it was obtained.

    ``source`` lets the ingestion layer warn when a title came purely from the
    document's own heading with no product name added from the filename — the
    case where a brochure whose product name lives only on the cover gets a
    generic, hard-to-retrieve title (see ``ingest._title_warning``).
    """

    title: str
    source: str  # "heading" | "heading+filename" | "filename"


# ATX heading: "## Chương II: ..." -> (level=2, "Chương II: ...")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

# Word tokenizer for title comparison (keeps Vietnamese letters, drops
# punctuation/whitespace consistently for both the display and normalized forms).
_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Vietnamese legal markers that may appear as/within a heading.
_HIER_RE = re.compile(
    r"\b(Chương|Mục|Điều|Khoản|Điểm)\b\s*([0-9IVXLCDM]+|\d+)",
    re.IGNORECASE,
)


def _heading_label(text: str) -> str:
    """Prefer a compact legal label ("Điều 5") when the heading contains one."""
    m = _HIER_RE.search(text)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    # Otherwise use the heading text up to a trailing ":" for brevity.
    return text.split(":", 1)[0].strip()


def _fold(word: str) -> str:
    """Diacritic- and case-insensitive form of a word (đ/Đ -> d)."""
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c)
    )
    return stripped.replace("đ", "d").replace("Đ", "d").lower()


def _reconcile_with_filename(heading: str, filename_title: str) -> tuple[str, bool]:
    """Merge a more complete filename into the heading. Returns (title, merged).

    Real product PDFs often carry a generic first heading ("Bảo hiểm liên kết
    chung") while the specific product name ("An Khang Như Ý") appears only on
    the cover artwork and in the filename. When the filename contains the heading
    as a contiguous run of words plus extra words, the heading alone drops the
    product name users actually search by — so merge them: keep the heading's
    text (diacritics intact) for the shared part and splice in the filename's
    extra words around it. Unrelated or junk filenames (no such overlap) leave
    the heading untouched (``merged=False``).
    """
    file_words = _WORD_RE.findall(filename_title)
    file_folded = [_fold(w) for w in file_words]
    head_folded = [_fold(w) for w in _WORD_RE.findall(heading)]
    if not head_folded or len(file_folded) <= len(head_folded):
        return heading, False
    span = len(head_folded)
    for i in range(len(file_folded) - span + 1):
        if file_folded[i : i + span] == head_folded:
            merged = [*file_words[:i], heading, *file_words[i + span :]]
            return " ".join(merged).strip(), True
    return heading, False


def derive_title(md: str, fallback: str) -> TitleResult:
    """Derive a document title and report how it was obtained.

    First H1 — else the first heading of any level — is the base; the any-level
    fallback matters for PDFs (Docling often classifies a cover title as H2).
    When the filename (``fallback``) is a strictly more complete version of that
    heading, it is merged in (``_reconcile_with_filename``) so the product name
    survives. With no heading at all, the filename is used directly.
    """
    heading: str | None = None
    for line in md.split("\n"):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        if len(m.group(1)) == 1:
            heading = m.group(2).strip()
            break
        if heading is None:
            heading = m.group(2).strip()
    if heading is None:
        return TitleResult(fallback, "filename")
    title, merged = _reconcile_with_filename(heading, fallback)
    return TitleResult(title, "heading+filename" if merged else "heading")


def title_from_markdown(md: str, fallback: str) -> str:
    """Convenience wrapper returning just the derived title (see ``derive_title``)."""
    return derive_title(md, fallback).title


def sections_from_markdown(
    md: str, *, doc_title: str | None = None
) -> list[ParsedSection]:
    """Split Markdown into ordered sections keyed by their heading path.

    Text before the first heading (if any) becomes an untitled lead section.
    Empty sections (heading with no body) are dropped.
    """
    lines = md.split("\n")
    # Stack of (level, label) building the current heading path.
    stack: list[tuple[int, str]] = []
    sections: list[ParsedSection] = []
    buf: list[str] = []

    def current_path() -> str:
        labels = [label for _, label in stack]
        return " > ".join(labels) if labels else (doc_title or "")

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append(ParsedSection(section_path=current_path(), text=body))
        buf.clear()

    for line in lines:
        m = _HEADING_RE.match(line)
        if not m:
            buf.append(line)
            continue
        # New heading: close out the previous section's body first.
        flush()
        level = len(m.group(1))
        label = _heading_label(m.group(2))
        # Pop deeper-or-equal levels, then push this heading.
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, label))

    flush()
    return sections
