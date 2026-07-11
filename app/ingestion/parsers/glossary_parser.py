"""Glossary parser: ``data/glossary/thuat_ngu.yaml`` -> ``ParsedDocument``.

Reuses the loader in ``query_expansion.py`` so the YAML schema stays defined
in one place (skill, section 4). Each entry becomes its own section — keyed by
the canonical term — with a Markdown+LaTeX body (symbol, synonyms, definition)
so it chunks/embeds/cites like any other document, indexed as
``doc_type: "glossary"`` for authoritative definition lookups.
"""

from __future__ import annotations

from pathlib import Path

from app.models.schemas import DocType, ParsedDocument, ParsedSection
from app.retrieval.query_expansion import GlossaryEntry, load_glossary

DOC_TITLE = "Từ điển thuật ngữ định phí bảo hiểm"


def _entry_to_section(entry: GlossaryEntry) -> ParsedSection:
    """Render one glossary entry as a Markdown+LaTeX section."""
    lines = [f"**{entry.term}**"]
    if entry.symbol:
        lines.append(f"Ký hiệu: ${entry.symbol}$")
    if entry.synonyms:
        lines.append(f"Đồng nghĩa: {', '.join(entry.synonyms)}")
    if entry.definition:
        lines.append(entry.definition)
    return ParsedSection(section_path=entry.term, text="\n\n".join(lines))


def parse_glossary(
    path: str | Path, *, doc_type: DocType = DocType.GLOSSARY
) -> ParsedDocument:
    """Parse the glossary YAML file into one section per term."""
    p = Path(path)
    entries = load_glossary(p)
    sections = [_entry_to_section(entry) for entry in entries]
    return ParsedDocument(
        doc_title=DOC_TITLE,
        doc_type=doc_type,
        sections=sections,
        source_path=str(p),
    )
