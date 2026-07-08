"""Formula-region OCR (STUB — Phase 1 placeholder).

PP-FormulaNet (via PaddleOCR PP-StructureV3) or Qwen2.5-VL prompted to transcribe
a formula region as LaTeX. Cross-check actuarial pre-subscript notation
(e.g. ``{}_np_x``) against the glossary; tag low-confidence output for review.
See skill section 1 (actuarial notation warning).
"""

from __future__ import annotations

# TODO(phase-ingestion): implement region_to_latex(image) -> str.
