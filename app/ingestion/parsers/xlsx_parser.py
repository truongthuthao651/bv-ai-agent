"""XLSX parser (STUB — Phase 1 placeholder).

One Markdown table per sheet. If a sheet exceeds the chunk budget, split by row
groups and REPEAT the header row in each group. Forward-fill merged cells. Ingest
computed values, not formulas. Returns a ``ParsedDocument``. See skill section 1.
"""

from __future__ import annotations

# TODO(phase-ingestion): implement parse_xlsx(path) -> ParsedDocument.
