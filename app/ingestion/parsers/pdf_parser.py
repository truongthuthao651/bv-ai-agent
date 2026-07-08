"""PDF parser (STUB — Phase 1 placeholder).

Docling with ``do_formula_enrichment=True`` so formulas emerge as LaTeX. If the
text layer averages < PDF_MIN_CHARS_PER_PAGE chars/page, route to ocr.py
(PaddleOCR, lang="vi"); never silently return empty text. Extract figure regions
via figure_extract.py. Returns a ``ParsedDocument``. See skill section 1.
"""

from __future__ import annotations

# TODO(phase-ingestion): implement parse_pdf(path) -> ParsedDocument.
