"""Chunking tests — equation/table hard constraints (skill, section 3)."""

from __future__ import annotations

from app.ingestion.chunking import chunk_document, default_token_counter
from app.models.schemas import DocType, ParsedDocument, ParsedSection


def _doc(text: str) -> ParsedDocument:
    return ParsedDocument(
        doc_title="T",
        doc_type=DocType.OTHER,
        sections=[ParsedSection(section_path="Điều 5", text=text)],
    )


def _balanced_dollars(s: str) -> bool:
    return s.count("$") % 2 == 0


def test_display_equation_kept_with_definition() -> None:
    text = (
        "Phí thuần được xác định theo nguyên tắc cân bằng giá trị hiện tại:\n\n"
        "$$P = \\frac{A}{\\ddot{a}}$$\n\n"
        "trong đó:\n\n"
        "- $A$ là giá trị hiện tại của quyền lợi;\n"
        "- $\\ddot{a}$ là niên kim nhân thọ."
    )
    # Tiny budget would normally split, but the equation unit must stay whole.
    chunks = chunk_document(_doc(text), "d1", max_tokens=15, overlap_pct=0.1)
    eq = [c for c in chunks if "$$" in c.display_text]
    assert len(eq) == 1
    body = eq[0].display_text
    assert "P = \\frac{A}{\\ddot{a}}" in body
    assert "trong đó" in body
    assert "niên kim" in body


def test_no_chunk_splits_inline_math() -> None:
    text = "\n\n".join(
        f"Đoạn số {i} có công thức $x_{i} = {i}$ ở giữa." for i in range(20)
    )
    chunks = chunk_document(_doc(text), "d2", max_tokens=30, overlap_pct=0.12)
    assert len(chunks) > 1  # actually split
    for c in chunks:
        assert _balanced_dollars(c.display_text)


def test_oversized_table_repeats_header() -> None:
    rows = "\n".join(f"| A{i} | B{i} | C{i} |" for i in range(12))
    text = "| Cột 1 | Cột 2 | Cột 3 |\n| --- | --- | --- |\n" + rows
    chunks = chunk_document(_doc(text), "d3", max_tokens=25, overlap_pct=0.1)
    table_chunks = [c for c in chunks if "| Cột 1 |" in c.display_text]
    # Split into multiple groups, each carrying the header row.
    assert len(table_chunks) > 1
    for c in table_chunks:
        assert "| Cột 1 | Cột 2 | Cột 3 |" in c.display_text
        for line in c.display_text.split("\n"):
            if line.strip():  # every non-empty line is a complete table row
                assert line.lstrip().startswith("|")


def test_table_keeps_preceding_caption() -> None:
    text = (
        "Lãi suất cam kết tối thiểu theo năm hợp đồng "
        "(không phải tỷ lệ bồi thường):\n\n"
        "| Năm hợp đồng | Lãi suất cam kết tối thiểu (%) |\n"
        "| --- | --- |\n"
        "| Năm 1 | 2.5 |\n"
        "| Năm 2 | 2.0 |"
    )
    chunks = chunk_document(_doc(text), "d5", max_tokens=800)
    assert len(chunks) == 1
    body = chunks[0].display_text
    assert "Lãi suất cam kết tối thiểu" in body
    assert "| Năm 1 | 2.5 |" in body


def test_oversized_captioned_table_repeats_caption() -> None:
    rows = "\n".join(f"| Năm {i} | {i * 0.1:.1f} |" for i in range(1, 20))
    text = (
        "Lãi suất cam kết tối thiểu (%):\n\n"
        "| Năm hợp đồng | Lãi suất (%) |\n| --- | --- |\n" + rows
    )
    chunks = chunk_document(_doc(text), "d6", max_tokens=30, overlap_pct=0.1)
    table_chunks = [c for c in chunks if "| Lãi suất (%) |" in c.display_text]
    assert len(table_chunks) > 1
    for c in table_chunks:
        assert "Lãi suất cam kết tối thiểu" in c.display_text


def test_token_counter_used_for_budget() -> None:
    # A single short section under budget yields exactly one chunk.
    chunks = chunk_document(_doc("Một đoạn ngắn."), "d4", max_tokens=800)
    assert len(chunks) == 1
    assert default_token_counter("Một đoạn ngắn.") < 800


# --------------------------------------------------------------------------- #
# Parent-child chunking
# --------------------------------------------------------------------------- #


def _paragraphs(n: int) -> str:
    return "\n\n".join(
        f"Đoạn số {i} nói về quyền lợi bảo hiểm nhân thọ." for i in range(n)
    )


def test_children_are_smaller_and_carry_their_parent() -> None:
    chunks = chunk_document(
        _doc(_paragraphs(12)),
        "p1",
        max_tokens=120,
        overlap_pct=0.1,
        child_max_tokens=20,
    )
    assert len(chunks) > 1
    widened = [c for c in chunks if c.parent_text is not None]
    assert widened, "expected at least one child narrower than its parent"
    for c in widened:
        # The child is a slice of its parent, and strictly smaller.
        assert c.display_text in c.parent_text
        assert len(c.display_text) < len(c.parent_text)
        assert c.parent_index is not None


def test_children_of_one_parent_share_a_parent_index() -> None:
    chunks = chunk_document(
        _doc(_paragraphs(12)),
        "p2",
        max_tokens=120,
        overlap_pct=0.1,
        child_max_tokens=20,
    )
    by_parent: dict[int, list[str]] = {}
    for c in chunks:
        if c.parent_index is not None:
            by_parent.setdefault(c.parent_index, []).append(c.parent_text or "")
    assert any(len(v) > 1 for v in by_parent.values())
    for texts in by_parent.values():
        assert len(set(texts)) == 1  # one window per parent_index


def test_parents_match_flat_chunking() -> None:
    # Parents are exactly the chunks produced without the feature, so the
    # generation context is unchanged by turning parent-child chunking on.
    text = _paragraphs(12)
    flat = chunk_document(_doc(text), "p3", max_tokens=120, overlap_pct=0.1)
    nested = chunk_document(
        _doc(text), "p3", max_tokens=120, overlap_pct=0.1, child_max_tokens=20
    )
    parents = []
    for c in nested:
        window = c.parent_text or c.display_text
        if window not in parents:
            parents.append(window)
    assert parents == [c.display_text for c in flat]


def test_child_equal_to_parent_carries_no_parent_text() -> None:
    # Nothing to widen to: don't duplicate the text in the payload.
    chunks = chunk_document(
        _doc("Một đoạn ngắn."), "p4", max_tokens=800, child_max_tokens=250
    )
    assert len(chunks) == 1
    assert chunks[0].parent_text is None
    assert chunks[0].parent_index is None


def test_child_split_never_breaks_an_equation_unit() -> None:
    text = (
        "Phí thuần được xác định theo nguyên tắc cân bằng giá trị hiện tại:\n\n"
        "$$P = \\frac{A}{\\ddot{a}}$$\n\n"
        "trong đó:\n\n"
        "- $A$ là giá trị hiện tại của quyền lợi;\n"
        "- $\\ddot{a}$ là niên kim nhân thọ."
    )
    chunks = chunk_document(
        _doc(text), "p5", max_tokens=800, overlap_pct=0.1, child_max_tokens=5
    )
    eq = [c for c in chunks if "$$" in c.display_text]
    assert len(eq) == 1  # the unit stayed whole despite the tiny child budget
    assert "trong đó" in eq[0].display_text
    for c in chunks:
        assert _balanced_dollars(c.display_text)


def test_child_split_row_splits_an_oversized_table() -> None:
    rows = "\n".join(f"| Năm {i} | {i * 0.1:.1f} |" for i in range(1, 20))
    text = (
        "Lãi suất cam kết tối thiểu (%):\n\n"
        "| Năm hợp đồng | Lãi suất (%) |\n| --- | --- |\n" + rows
    )
    chunks = chunk_document(
        _doc(text), "p6", max_tokens=800, overlap_pct=0.1, child_max_tokens=30
    )
    # The table fits one parent but not one child, so children are row groups —
    # each still carrying the header and the caption that names the metric.
    table_children = [c for c in chunks if "| Lãi suất (%) |" in c.display_text]
    assert len(table_children) > 1
    for c in table_children:
        assert "Lãi suất cam kết tối thiểu" in c.display_text
        assert "Lãi suất cam kết tối thiểu" in (c.parent_text or c.display_text)
