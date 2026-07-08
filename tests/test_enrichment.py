"""Enrichment tests — embed_text vs display_text separation (skill, section 2)."""

from __future__ import annotations

from app.ingestion.enrichment import enrich_chunks, has_math
from app.models.schemas import Chunk, DocType


def _chunk(display: str) -> Chunk:
    return Chunk(
        doc_id="d",
        doc_title="t",
        section_path="s",
        doc_type=DocType.OTHER,
        display_text=display,
        embed_text="Tài liệu: t > s\n\n" + display,
        chunk_index=0,
    )


def test_has_math() -> None:
    assert has_math("phí $P = A$ đây")
    assert has_math("$$x = 1$$")
    assert not has_math("không có công thức nào")


def test_verbalization_appends_to_embed_only() -> None:
    c = _chunk("Công thức phí thuần: $P = A/\\ddot{a}$.")
    display_before = c.display_text
    out = enrich_chunks([c], enabled=True, verbalize=lambda _: "Tính phí thuần năm.")
    assert out[0].display_text == display_before  # display untouched
    assert "Tính phí thuần năm." in out[0].embed_text


def test_non_math_chunk_untouched() -> None:
    c = _chunk("Đoạn văn không có công thức.")
    embed_before = c.embed_text
    out = enrich_chunks([c], enabled=True, verbalize=lambda _: "KHÔNG NÊN THÊM")
    assert out[0].embed_text == embed_before


def test_disabled_skips_verbalization() -> None:
    c = _chunk("Có $x=1$ ở đây.")
    embed_before = c.embed_text
    out = enrich_chunks([c], enabled=False, verbalize=lambda _: "X")
    assert out[0].embed_text == embed_before
