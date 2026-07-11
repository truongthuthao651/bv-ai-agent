"""Retrieval tests: glossary expansion, query rewrite gating, RRF fusion, rerank.

Everything here is pure-Python / injected fakes — no Docker, Ollama, or Qdrant
needed (skill sections 4-5).
"""

from __future__ import annotations

from app.models.schemas import ChatMessage, DocType, Hit, QdrantPayload
from app.retrieval.query_expansion import GlossaryEntry, expand_query
from app.retrieval.query_rewrite import rewrite_standalone
from app.retrieval.reranker import rerank
from app.retrieval.retriever import rrf_fuse

_GLOSSARY = (
    GlossaryEntry(
        term="phí thuần",
        synonyms=["net premium", "phí rủi ro thuần"],
        symbol="P",
        definition="...",
    ),
    GlossaryEntry(
        term="dự phòng nghiệp vụ",
        synonyms=["reserve", "dự phòng toán học"],
        symbol="_tV_x",
        definition="...",
    ),
)


# --------------------------------------------------------------------------- #
# Query expansion (glossary, no LLM)
# --------------------------------------------------------------------------- #


def test_expand_query_adds_missing_synonyms() -> None:
    out = expand_query("net premium là gì?", glossary=_GLOSSARY)
    assert "phí thuần" in out
    assert "phí rủi ro thuần" in out
    assert "net premium là gì?" in out  # original query preserved verbatim


def test_expand_query_no_match_returns_unchanged() -> None:
    query = "Thời hạn giải quyết quyền lợi là bao lâu?"
    assert expand_query(query, glossary=_GLOSSARY) == query


def test_expand_query_does_not_duplicate_terms_already_present() -> None:
    out = expand_query("phí thuần và net premium khác gì nhau?", glossary=_GLOSSARY)
    # Both surface forms already present -> only the missing synonym is added.
    assert out.count("net premium") == 1
    assert "phí rủi ro thuần" in out


def test_expand_query_empty_glossary_is_noop() -> None:
    query = "net premium là gì?"
    assert expand_query(query, glossary=()) == query


def test_expand_query_disabled_flag_returns_unchanged() -> None:
    # Even with a matching glossary term, disabling expansion is a no-op.
    query = "net premium là gì?"
    assert expand_query(query, enabled=False, glossary=_GLOSSARY) == query


def test_expand_query_enabled_flag_still_expands() -> None:
    out = expand_query("net premium là gì?", enabled=True, glossary=_GLOSSARY)
    assert "phí thuần" in out


# --------------------------------------------------------------------------- #
# Query rewrite (LLM, gated + injectable)
# --------------------------------------------------------------------------- #


def test_rewrite_skipped_without_history() -> None:
    out = rewrite_standalone(
        [],
        "còn phí gộp thì sao?",
        enabled=True,
        rewrite=lambda _: "SHOULD NOT BE CALLED",
    )
    assert out == "còn phí gộp thì sao?"


def test_rewrite_skipped_when_disabled() -> None:
    history = [ChatMessage(role="user", content="Phí thuần của An Tâm Bảo Vệ là gì?")]
    out = rewrite_standalone(
        history,
        "còn phí gộp thì sao?",
        enabled=False,
        rewrite=lambda _: "SHOULD NOT BE CALLED",
    )
    assert out == "còn phí gộp thì sao?"


def test_rewrite_uses_llm_when_enabled_with_history() -> None:
    history = [
        ChatMessage(role="user", content="Phí thuần của An Tâm Bảo Vệ là gì?"),
        ChatMessage(role="assistant", content="Phí thuần là ..."),
    ]
    out = rewrite_standalone(
        history,
        "còn phí gộp thì sao?",
        enabled=True,
        rewrite=lambda prompt: "Phí gộp của sản phẩm An Tâm Bảo Vệ là gì?",
    )
    assert out == "Phí gộp của sản phẩm An Tâm Bảo Vệ là gì?"


def test_rewrite_falls_back_to_original_on_empty_llm_output() -> None:
    history = [ChatMessage(role="user", content="Phí thuần là gì?")]
    out = rewrite_standalone(
        history, "còn phí gộp?", enabled=True, rewrite=lambda _: ""
    )
    assert out == "còn phí gộp?"


# --------------------------------------------------------------------------- #
# RRF fusion (retriever)
# --------------------------------------------------------------------------- #


def test_rrf_fuse_ranks_items_in_both_lists_highest() -> None:
    dense = ["a", "b", "c"]
    sparse = ["b", "a", "d"]
    scores = rrf_fuse([dense, sparse], k=60)
    ranked = sorted(scores, key=lambda pid: scores[pid], reverse=True)
    # "a" and "b" each appear near the top of both lists -> outrank "c"/"d",
    # which each appear in only one list (rank 3, same rank in a single list).
    assert set(ranked[:2]) == {"a", "b"}
    assert scores["a"] == scores["b"]
    assert scores["c"] == scores["d"]
    assert scores["a"] > scores["c"]


def test_rrf_fuse_single_ranking_matches_reciprocal_rank() -> None:
    scores = rrf_fuse([["x", "y", "z"]], k=60)
    assert scores["x"] == 1.0 / 61
    assert scores["y"] == 1.0 / 62
    assert scores["x"] > scores["y"] > scores["z"]


def test_rrf_fuse_empty_input() -> None:
    assert rrf_fuse([], k=60) == {}


# --------------------------------------------------------------------------- #
# Reranking (injected score_fn, no model load)
# --------------------------------------------------------------------------- #


def _hit(point_id: str, text: str) -> Hit:
    payload = QdrantPayload(
        doc_id="d1",
        doc_title="Tài liệu",
        section_path="Điều 1",
        doc_type=DocType.OTHER,
        display_text=text,
        chunk_index=0,
        ingested_at="2026-01-01T00:00:00+00:00",
    )
    return Hit(point_id=point_id, score=0.0, payload=payload)


def test_rerank_reorders_by_score_and_cuts_to_top_k() -> None:
    hits = [_hit("1", "doc-low"), _hit("2", "doc-high"), _hit("3", "doc-mid")]
    fake_scores = {"doc-low": 0.0, "doc-high": 1.0, "doc-mid": 0.5}

    def score_fn(_query: str, docs: list[str]) -> list[float]:
        return [fake_scores[d] for d in docs]

    ranked = rerank("query", hits, top_k=2, score_fn=score_fn)
    assert [h.point_id for h in ranked] == ["2", "3"]
    assert ranked[0].score == 1.0


def test_rerank_empty_hits() -> None:
    assert rerank("query", [], score_fn=lambda _q, _d: []) == []
