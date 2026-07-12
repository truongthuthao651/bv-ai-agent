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

from app.models.schemas import ParsedSection

# ATX heading: "## Chương II: ..." -> (level=2, "Chương II: ...")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

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


def title_from_markdown(md: str, fallback: str) -> str:
    """Doc title from the first H1 — else the first heading of any level, else
    ``fallback`` (usually the filename, which loses Vietnamese diacritics).

    The any-level fallback matters for PDFs: Docling often classifies a cover
    title as H2, and a proper diacritics title is what citations display.
    """
    first_heading: str | None = None
    for line in md.split("\n"):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        if len(m.group(1)) == 1:
            return m.group(2).strip()
        if first_heading is None:
            first_heading = m.group(2).strip()
    return first_heading or fallback


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
