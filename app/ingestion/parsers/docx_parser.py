"""DOCX and Markdown parsers -> ParsedDocument.

DOCX is routed through **pandoc** (``gfm+tex_math_dollars``) so Word OMML
equations become LaTeX. NEVER use python-docx as the primary text path — it
silently DROPS equations (skill, section 1). Markdown files are already canonical
and go straight through the shared sectionizer.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from app.ingestion.parsers.markdown import sections_from_markdown, title_from_markdown
from app.models.schemas import DocType, ParsedDocument


def title_from_path(path: Path) -> str:
    """Fallback human title from a filename."""
    return path.stem.replace("_", " ").replace("-", " ").strip()


def parse_markdown(
    path: str | Path, *, doc_type: DocType = DocType.OTHER
) -> ParsedDocument:
    """Parse a ``.md`` file (already canonical Markdown+LaTeX)."""
    p = Path(path)
    md = unicodedata.normalize("NFC", p.read_text(encoding="utf-8"))
    title = title_from_markdown(md, title_from_path(p))
    sections = sections_from_markdown(md, doc_title=title)
    return ParsedDocument(
        doc_title=title,
        doc_type=doc_type,
        sections=sections,
        source_path=str(p),
    )


def parse_docx(
    path: str | Path, *, doc_type: DocType = DocType.OTHER
) -> ParsedDocument:
    """Parse a ``.docx`` via pandoc, preserving OMML equations as LaTeX."""
    import pypandoc  # imported lazily so the module imports without the dep

    p = Path(path)
    md = pypandoc.convert_file(
        str(p),
        to="gfm+tex_math_dollars",
        format="docx",
    )
    md = unicodedata.normalize("NFC", md)
    title = title_from_markdown(md, title_from_path(p))
    sections = sections_from_markdown(md, doc_title=title)
    return ParsedDocument(
        doc_title=title,
        doc_type=doc_type,
        sections=sections,
        source_path=str(p),
    )
