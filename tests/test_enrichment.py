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


def test_ollama_verbalize_sends_matching_context_window(monkeypatch) -> None:
    # 2026-08-06: the sibling omission in query_rewrite.py/verify.py forced a
    # full model reload whenever this call and a live chat generation hit
    # the same Ollama instance back-to-back (e.g. ingestion running
    # alongside a live server) -- fixed here too for consistency.
    import app.ingestion.enrichment as enrichment_module
    from app.config.settings import settings

    captured: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": "Mô tả công thức."}

    def fake_post(url, json, **kwargs):
        captured.update(json)
        return _Resp()

    monkeypatch.setattr(enrichment_module.httpx, "post", fake_post)
    out = enrichment_module._ollama_verbalize("$x = 1$")
    assert out == "Mô tả công thức."
    assert captured["options"]["num_ctx"] == settings.llm_context_window


def test_metric_hint_appended_for_interest_table_even_when_enrichment_off() -> None:
    display = (
        "Lãi suất cam kết tối thiểu theo năm hợp đồng:\n\n"
        "| Năm hợp đồng | Lãi suất cam kết tối thiểu (%) |\n"
        "| --- | --- |\n"
        "| Năm 1 | 2.5 |"
    )
    c = _chunk(display)
    out = enrich_chunks([c], enabled=False, verbalize=lambda _: "NO")
    assert out[0].display_text == display  # display untouched
    assert "Loại chỉ số:" in out[0].embed_text
    assert "lãi suất cam kết" in out[0].embed_text
    assert "không phải tỷ lệ bồi thường" in out[0].embed_text
