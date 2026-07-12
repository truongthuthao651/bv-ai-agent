"""File-type detection -> correct parser.

Maps a file (by extension) to a parser returning a ``ParsedDocument``.
Currently handled: Markdown, DOCX, XLSX, PDF (text-layer), and the glossary
YAML; image/scan parsers arrive with the OCR increment and raise
``NotImplementedError``.
"""

from __future__ import annotations

from pathlib import Path

from app.ingestion.parsers.docx_parser import parse_docx, parse_markdown
from app.ingestion.parsers.glossary_parser import parse_glossary
from app.ingestion.parsers.pdf_parser import parse_pdf
from app.ingestion.parsers.xlsx_parser import parse_xlsx
from app.models.schemas import DocType, ParsedDocument

# Default doc_type per extension when the caller doesn't specify one.
_DEFAULT_DOCTYPE: dict[str, DocType] = {
    ".md": DocType.OTHER,
    ".markdown": DocType.OTHER,
    ".docx": DocType.OTHER,
    ".pdf": DocType.POLICY,
    ".xlsx": DocType.SPREADSHEET,
    ".xls": DocType.SPREADSHEET,
    ".png": DocType.IMAGE,
    ".jpg": DocType.IMAGE,
    ".jpeg": DocType.IMAGE,
    ".yaml": DocType.GLOSSARY,
    ".yml": DocType.GLOSSARY,
}


def route_to_parser(
    path: str | Path, *, doc_type: DocType | None = None
) -> ParsedDocument:
    """Detect the file type and run the matching parser.

    ``doc_type`` overrides the extension default (e.g. tagging a DOCX as a
    "procedure"). Raises ``NotImplementedError`` for types not yet supported and
    ``ValueError`` for unknown extensions.
    """
    p = Path(path)
    ext = p.suffix.lower()
    resolved_type = doc_type or _DEFAULT_DOCTYPE.get(ext, DocType.OTHER)

    if ext in (".md", ".markdown"):
        return parse_markdown(p, doc_type=resolved_type)
    if ext == ".docx":
        return parse_docx(p, doc_type=resolved_type)
    if ext in (".yaml", ".yml"):
        return parse_glossary(p, doc_type=resolved_type)
    if ext == ".xlsx":
        return parse_xlsx(p, doc_type=resolved_type)
    if ext == ".pdf":
        return parse_pdf(p, doc_type=resolved_type)
    if ext == ".xls":
        raise NotImplementedError(
            "Legacy '.xls' is not supported; re-save the file as '.xlsx' and retry."
        )
    if ext in (".png", ".jpg", ".jpeg"):
        raise NotImplementedError(f"Parser for '{ext}' arrives with the OCR increment.")
    raise ValueError(f"Unsupported file type: '{ext}' ({p.name})")
