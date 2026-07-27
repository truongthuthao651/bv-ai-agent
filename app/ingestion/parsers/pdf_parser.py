"""PDF parser: Docling -> Markdown+LaTeX -> sections.

Docling runs with ``do_formula_enrichment`` (settings) so rendered formulas come
out as LaTeX, and with local weights (``settings.docling_models_path``,
pre-fetched by setup_models.sh) so parsing stays offline. The exported Markdown
goes through cleaning (NFC + running header/footer strip — PDFs are the one
format where page furniture leaks into the text) and then the shared
sectionizer, like every other parser.

A PDF whose text layer averages fewer than ``settings.pdf_min_chars_per_page``
characters per page is almost certainly a scan; per the skill we never silently
return empty text, so it raises a clear error until the OCR increment lands.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.ingestion.cleaning import normalize_text, strip_headers_footers
from app.ingestion.parsers.docx_parser import title_from_path
from app.ingestion.parsers.markdown import (
    PAGE_BREAK_SENTINEL,
    derive_title,
    sections_from_markdown,
)
from app.models.schemas import DocType, ParsedDocument

logger = logging.getLogger(__name__)

# Docling emits placeholders like "<!-- image -->" for undecoded regions; they
# are noise for embedding and display alike.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


@lru_cache
def _get_converter() -> Any:
    """Build and cache the Docling converter (heavy model load, once per process)."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    backend_kwargs: dict[str, Any] = {}
    if settings.pdf_backend == "pypdfium2":
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

        backend_kwargs["backend"] = PyPdfiumDocumentBackend
    elif settings.pdf_backend != "docling-parse":
        raise ValueError(
            f"Unknown PDF_BACKEND '{settings.pdf_backend}' "
            "(expected 'pypdfium2' or 'docling-parse')"
        )

    opts = PdfPipelineOptions()
    opts.do_formula_enrichment = settings.do_formula_enrichment
    models_dir = settings.docling_models_path
    if models_dir.is_dir() and any(models_dir.iterdir()):
        # Offline weights from setup_models.sh; a missing or EMPTY dir is
        # ignored (docling would hard-fail on it) and Docling downloads on
        # first use instead (cached under HF_HOME -> host-mounted ./models).
        opts.artifacts_path = models_dir
    logger.info(
        "Loading Docling PDF pipeline (backend=%s, formula_enrichment=%s)",
        settings.pdf_backend,
        settings.do_formula_enrichment,
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=opts, **backend_kwargs)
        }
    )


def _convert_with_docling(path: Path) -> tuple[str, int]:
    """Run Docling on a PDF; returns (markdown, page_count). Mocked in tests.

    The markdown carries ``PAGE_BREAK_SENTINEL`` at every page boundary so the
    sectionizer can stamp each section with its starting page (citation
    deep-links). The marker survives cleaning and is stripped during sectioning.
    """
    result = _get_converter().convert(str(path))
    md = result.document.export_to_markdown(page_break_placeholder=PAGE_BREAK_SENTINEL)
    n_pages = max(len(result.document.pages), 1)
    return md, n_pages


def parse_pdf(
    path: str | Path, *, doc_type: DocType = DocType.POLICY
) -> ParsedDocument:
    """Parse a text-layer PDF into cleaned, sectioned Markdown+LaTeX."""
    p = Path(path)
    md, n_pages = _convert_with_docling(p)

    density = len("".join(md.split())) / n_pages
    if density < settings.pdf_min_chars_per_page:
        raise NotImplementedError(
            f"'{p.name}' has no usable text layer (~{density:.0f} chars/page — "
            "likely a scan). Scanned-PDF OCR arrives in the OCR increment; "
            "re-export the PDF with a text layer or use .docx/.md for now."
        )

    md = _HTML_COMMENT_RE.sub("", md)
    md = unicodedata.normalize("NFC", md)
    md = strip_headers_footers(normalize_text(md))
    title = derive_title(md, title_from_path(p))
    sections = sections_from_markdown(md, doc_title=title.title, track_pages=True)
    return ParsedDocument(
        doc_title=title.title,
        doc_type=doc_type,
        sections=sections,
        source_path=str(p),
        title_source=title.source,
    )
