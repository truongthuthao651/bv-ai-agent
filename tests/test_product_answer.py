"""Tests for product-scoped answer cleanup."""

from __future__ import annotations

from app.generation.product_answer import (
    polish_product_answer,
    strip_actuarial_formula_blocks,
    strip_foreign_product_citations,
    strip_general_knowledge_section,
)
from app.generation.prompts import GENERAL_KNOWLEDGE_HEADING
from app.models.schemas import DocType, Hit, QdrantPayload


def _policy_hit(title: str, *, n: int = 1) -> Hit:
    return Hit(
        point_id=str(n),
        score=0.9,
        payload=QdrantPayload(
            doc_id=f"d{n}",
            doc_title=title,
            section_path="Điều 1",
            display_text="body",
            doc_type=DocType.POLICY,
            chunk_index=0,
            ingested_at="2026-01-01T00:00:00+00:00",
        ),
    )


def test_strip_general_knowledge_section() -> None:
    body = f"Quyền lợi chính [1].\n\n{GENERAL_KNOWLEDGE_HEADING}\nTextbook note."
    assert strip_general_knowledge_section(body) == "Quyền lợi chính [1]."


def test_strip_actuarial_formula_blocks() -> None:
    mixed = (
        "Loại sản phẩm: liên kết chung.\n\n"
        "Phí thuần năm cho hợp đồng bảo hiểm tử kỳ n năm được tính theo công thức [5].\n\n"
        "Các trường hợp loại trừ [3]."
    )
    out = strip_actuarial_formula_blocks(mixed)
    assert "Phí thuần năm" not in out
    assert "loại trừ" in out


def test_strip_foreign_product_citations() -> None:
    known = [
        "Bảo hiểm Liên kết chung An Tâm Hoạch Định",
        'Quy tắc, Điều khoản Sản phẩm Bảo hiểm Tử kỳ "An Tâm Bảo Vệ"',
    ]
    hits = [_policy_hit(known[0], n=1), _policy_hit(known[1], n=2)]
    answer = "Phí liên kết [1].\n\nPhí thuần tử kỳ [2]."
    out = strip_foreign_product_citations(
        answer, hits, "An Tâm Hoạch Định", known_titles=known
    )
    assert "[2]" not in out
    assert "[1]" in out


def test_polish_product_summary_turn() -> None:
    known = [
        "Bảo hiểm Liên kết chung An Tâm Hoạch Định",
        'Quy tắc, Điều khoản Sản phẩm Bảo hiểm Tử kỳ "An Tâm Bảo Vệ"',
    ]
    hits = [_policy_hit(known[0], n=1), _policy_hit(known[1], n=2)]
    raw = (
        "Loại sản phẩm: liên kết chung [1].\n\n"
        "Phí thuần năm cho hợp đồng bảo hiểm tử kỳ [2].\n\n"
        f"{GENERAL_KNOWLEDGE_HEADING}\nKiến thức giáo khoa."
    )
    out = polish_product_answer(
        raw,
        hits=hits,
        product_labels=["An Tâm Hoạch Định"],
        product_named=True,
        product_summary=True,
        known_titles=known,
    )
    assert GENERAL_KNOWLEDGE_HEADING not in out
    assert "Phí thuần năm" not in out
    assert "[2]" not in out
