"""Post-process grounded answers for product-scoped turns.

Deterministic cleanup when the model disobeys product-named / summary rules —
e.g. appends "Kiến thức chung" on a named-product question, or regurgitates a
term-life pricing formula from an earlier turn when asked for a product summary.
"""

from __future__ import annotations

import re

from app.generation.prompts import GENERAL_KNOWLEDGE_HEADING
from app.models.schemas import DocType, Hit
from app.retrieval.product_scope import resolve_product_titles, title_covers_product
from app.text_utils import fold_text

_ACTUARIAL_BLOCK_MARKERS: tuple[str, ...] = (
    "phi thuan nam cho hop dong bao hiem tu ky",
    "nien kim nhan tho tam thoi",
    "gia tri hien tai cua quyen loi tu vong",
)

_GLOSSARY_ASIDE_MARKERS: tuple[str, ...] = (
    "phi thuan",
    "nien kim",
    "dinh phi la",
)

_CITATION_RE = re.compile(r"\[\d+\]")


def strip_general_knowledge_section(answer: str) -> str:
    """Remove an model-authored general-knowledge supplement."""
    idx = answer.find(GENERAL_KNOWLEDGE_HEADING)
    return answer[:idx].rstrip() if idx != -1 else answer


def strip_actuarial_formula_blocks(answer: str) -> str:
    """Drop paragraphs that look like term-life actuarial pricing formulas."""
    kept: list[str] = []
    for block in re.split(r"\n\s*\n", answer):
        folded = fold_text(block)
        if any(marker in folded for marker in _ACTUARIAL_BLOCK_MARKERS):
            continue
        kept.append(block)
    return "\n\n".join(kept).strip()


def _foreign_citation_indices(
    answer: str,
    hits: list[Hit],
    product_label: str,
    *,
    known_titles: list[str] | None,
) -> set[int]:
    """Citation numbers in ``answer`` that point at another product's policy doc."""
    if not hits or not product_label.strip():
        return set()
    foreign: set[int] = set()
    for n, hit in enumerate(hits, start=1):
        marker = f"[{n}]"
        if marker not in answer:
            continue
        if hit.payload.doc_type != DocType.POLICY:
            continue
        if title_covers_product(
            hit.payload.doc_title, product_label, known_titles=known_titles
        ):
            continue
        foreign.add(n)
    return foreign


def strip_foreign_product_citations(
    answer: str,
    hits: list[Hit],
    product_label: str,
    *,
    known_titles: list[str] | None = None,
) -> str:
    """Remove paragraphs that cite policy chunks from a different product."""
    foreign = _foreign_citation_indices(
        answer, hits, product_label, known_titles=known_titles
    )
    if not foreign:
        return answer
    kept: list[str] = []
    for block in re.split(r"\n\s*\n", answer):
        markers = {int(m.group(0)[1:-1]) for m in _CITATION_RE.finditer(block)}
        if markers & foreign:
            continue
        kept.append(block)
    return "\n\n".join(kept).strip()


def strip_glossary_pricing_asides(answer: str, hits: list[Hit]) -> str:
    """Drop glossary-sourced pricing asides on product-summary turns."""
    if not answer.strip():
        return answer
    kept: list[str] = []
    for block in re.split(r"\n\s*\n", answer):
        folded = fold_text(block)
        if any(m in folded for m in _GLOSSARY_ASIDE_MARKERS) and _CITATION_RE.search(
            block
        ):
            nums = {int(m.group(0)[1:-1]) for m in _CITATION_RE.finditer(block)}
            if nums and all(
                0 < n <= len(hits)
                and (
                    hits[n - 1].payload.doc_type
                    in (DocType.GLOSSARY, DocType.REFERENCE)
                    or "tu dien" in fold_text(hits[n - 1].payload.doc_title)
                )
                for n in nums
            ):
                continue
        kept.append(block)
    return "\n\n".join(kept).strip()


def polish_product_answer(
    answer: str,
    *,
    hits: list[Hit],
    product_labels: list[str],
    product_named: bool,
    product_summary: bool,
    known_titles: list[str] | None = None,
) -> str:
    """Apply deterministic product-scope cleanup to a grounded model answer."""
    if not answer.strip():
        return answer
    if product_named:
        answer = strip_general_knowledge_section(answer)
    if product_summary:
        answer = strip_actuarial_formula_blocks(answer)
        answer = strip_glossary_pricing_asides(answer, hits)
    if product_named and len(product_labels) == 1:
        answer = strip_foreign_product_citations(
            answer,
            hits,
            product_labels[0],
            known_titles=known_titles,
        )
    return answer.strip()


def foreign_policy_hits(
    hits: list[Hit],
    product_labels: list[str],
    *,
    known_titles: list[str] | None = None,
) -> list[Hit]:
    """Policy chunks in ``hits`` that belong to a product other than the named one."""
    if len(product_labels) != 1:
        return []
    known = known_titles or []
    target_titles = resolve_product_titles(product_labels[0], known)
    if not target_titles:
        return []
    target_cf = {t.casefold() for t in target_titles}
    known_cf = {t.casefold() for t in known}
    out: list[Hit] = []
    for hit in hits:
        if hit.payload.doc_type != DocType.POLICY:
            continue
        dt_cf = hit.payload.doc_title.casefold()
        if dt_cf in known_cf and dt_cf not in target_cf:
            out.append(hit)
    return out
