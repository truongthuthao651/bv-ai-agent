"""Retrieval tests: glossary expansion, query rewrite gating, RRF fusion, rerank.

Everything here is pure-Python / injected fakes — no Docker, Ollama, or Qdrant
needed (skill sections 4-5).
"""

from __future__ import annotations

from app.models.schemas import ChatMessage, DocType, Hit, QdrantPayload
from app.retrieval.conversation_scope import (
    active_scope,
    cited_doc_titles,
    ensure_prior_topic,
    ensure_scope,
    query_covers_scope,
)
from app.retrieval.product_scope import query_names_absent_product
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

_AKNY = "Bảo hiểm liên kết chung An Khang Như Ý"
_SOURCES = (
    f"Quyền lợi tử vong gồm...\n\n**Nguồn tham khảo:**\n"
    f"- [1] [{_AKNY}](http://localhost/documents/d1/view) — QUYỀN LỢI TỬ VONG\n"
    f"- [2] [{_AKNY}](http://localhost/documents/d1/view) — LOẠI TRỪ TRÁCH NHIỆM"
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
    # LLM rewriter is off, but the deterministic prior-topic safety net still
    # reattaches scenario details the short follow-up dropped.
    assert out.startswith("còn phí gộp thì sao?")
    assert "An Tâm Bảo Vệ" in out or "Phí thuần" in out


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


def test_rewrite_prompt_includes_scope_and_condenses_assistant() -> None:
    history = [
        ChatMessage(role="user", content="Quyền lợi An Khang Như Ý?"),
        ChatMessage(role="assistant", content=_SOURCES),
    ]
    captured: list[str] = []

    def fake(prompt: str) -> str:
        captured.append(prompt)
        return "KH mua An Khang Như Ý đi trượt tuyết có claim được không?"

    out = rewrite_standalone(
        history,
        "thế đi trượt tuyết thì sao?",
        scope=_AKNY,
        enabled=True,
        rewrite=fake,
    )
    assert captured and _AKNY in captured[0]
    assert "Tài liệu/sản phẩm đang được thảo luận" in captured[0]
    assert "Tài liệu đã trích dẫn" in captured[0]
    # Full sources block must not flood the rewrite prompt.
    assert "**Nguồn tham khảo:**" not in captured[0]
    assert "An Khang Như Ý" in out


def test_rewrite_ensure_scope_when_llm_drops_product_name() -> None:
    history = [
        ChatMessage(role="user", content="Quyền lợi An Khang Như Ý?"),
        ChatMessage(role="assistant", content=_SOURCES),
    ]
    out = rewrite_standalone(
        history,
        "thế đi trượt tuyết thì sao?",
        scope=_AKNY,
        enabled=True,
        # Model returns a standalone question but forgets the product.
        rewrite=lambda _: "Đi trượt tuyết thì có được claim không?",
    )
    assert _AKNY in out
    assert "trượt tuyết" in out


def test_rewrite_ensure_scope_even_when_rewrite_disabled() -> None:
    # Deterministic safety net independent of the LLM rewriter.
    out = rewrite_standalone(
        [ChatMessage(role="user", content="x")],
        "thế bị tử vong thì sao?",
        scope=_AKNY,
        enabled=False,
        rewrite=lambda _: "SHOULD NOT BE CALLED",
    )
    assert out.endswith(f"(tài liệu: {_AKNY})")


def test_rewrite_reattaches_prior_topic_when_llm_drops_scenario() -> None:
    # Exact failure mode from the UI: doc scope stuck, but skiing/diving dropped.
    prior = "KH đi trượt tuyết và lặn biển về claim QL thương tật có được không?"
    history = [
        ChatMessage(role="user", content=prior),
        ChatMessage(role="assistant", content=_SOURCES),
    ]
    out = rewrite_standalone(
        history,
        "thế tử vong thì sao",
        scope=_AKNY,
        enabled=True,
        rewrite=lambda _: "Thế tử vong thì sao",  # model forgot the scenario
    )
    assert "trượt tuyết" in out
    assert "lặn biển" in out
    assert "tử vong" in out.lower() or "Thế tử vong" in out
    assert _AKNY in out


def test_rewrite_skips_prior_topic_when_llm_already_kept_scenario() -> None:
    prior = "KH đi trượt tuyết và lặn biển về claim QL thương tật có được không?"
    history = [ChatMessage(role="user", content=prior)]
    good = "KH đi trượt tuyết và lặn biển về claim quyền lợi tử vong có được không?"
    out = rewrite_standalone(
        history, "thế tử vong thì sao", enabled=True, rewrite=lambda _: good
    )
    assert out == good
    assert "ngữ cảnh câu trước" not in out


# --------------------------------------------------------------------------- #
# Conversation scope (sticky product/doc across turns)
# --------------------------------------------------------------------------- #


def test_cited_doc_titles_from_sources_footer() -> None:
    assert cited_doc_titles(_SOURCES) == [_AKNY, _AKNY]


def test_active_scope_prefers_last_assistant_citations() -> None:
    history = [
        ChatMessage(role="user", content="Quyền lợi bảo hiểm An Khang Như Ý?"),
        ChatMessage(role="assistant", content=_SOURCES),
        ChatMessage(role="user", content="thế đi trượt tuyết thì sao?"),
    ]
    assert active_scope(history) == _AKNY


def test_active_scope_falls_back_to_user_product_phrase() -> None:
    history = [
        ChatMessage(
            role="user",
            content="Liệt kê quyền lợi của bảo hiểm an khang như ý",
        )
    ]
    scope = active_scope(history)
    assert scope is not None
    # product_span skips the generic leading "an"; distinctive tokens remain.
    assert query_covers_scope("An Khang Như Ý", scope)


def test_ensure_scope_injects_when_follow_up_drops_name() -> None:
    out = ensure_scope("thế đi trượt tuyết bị tử vong thì sao?", _AKNY)
    assert out.endswith(f"(tài liệu: {_AKNY})")


def test_ensure_scope_noop_when_query_already_names_product() -> None:
    q = "KH mua An Khang Như Ý đi trượt tuyết có claim được không?"
    assert ensure_scope(q, _AKNY) == q


def test_ensure_scope_noop_when_user_switches_product() -> None:
    q = "còn bảo hiểm An Thịnh Phúc Niên thì sao?"
    assert ensure_scope(q, _AKNY) == q


def test_query_covers_scope_diacritic_insensitive() -> None:
    assert query_covers_scope("quyen loi an khang nhu y", _AKNY)


def test_ensure_prior_topic_injects_skiing_diving_scenario() -> None:
    prior = "KH đi trượt tuyết và lặn biển về claim QL thương tật có được không?"
    history = [ChatMessage(role="user", content=prior)]
    out = ensure_prior_topic("thế tử vong thì sao", history)
    assert "trượt tuyết" in out
    assert "lặn biển" in out
    assert out.startswith("thế tử vong thì sao")


def test_ensure_prior_topic_noop_for_full_new_question() -> None:
    history = [
        ChatMessage(
            role="user",
            content="KH đi trượt tuyết và lặn biển về claim QL thương tật?",
        )
    ]
    q = "Thời hạn giải quyết quyền lợi bảo hiểm là bao lâu?"
    assert ensure_prior_topic(q, history) == q


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
        return [next(v for k, v in fake_scores.items() if k in d) for d in docs]

    ranked = rerank("query", hits, top_k=2, score_fn=score_fn)
    assert [h.point_id for h in ranked] == ["2", "3"]
    assert ranked[0].score == 1.0


def test_rerank_scores_against_title_and_section_prefixed_text() -> None:
    # The cross-encoder must see which document/section a chunk belongs to, so
    # queries naming a product still rank its benefit clauses (whose body never
    # repeats the product name) above chunks that merely mention the name.
    hits = [_hit("1", "body text")]
    seen: list[str] = []

    def score_fn(_query: str, docs: list[str]) -> list[float]:
        seen.extend(docs)
        return [1.0] * len(docs)

    rerank("query", hits, top_k=1, score_fn=score_fn)
    assert seen == ["Tài liệu: Tài liệu > Điều 1\n\nbody text"]


def test_rerank_empty_hits() -> None:
    assert rerank("query", [], score_fn=lambda _q, _d: []) == []


def _child_hit(point_id: str, text: str, parent_index: int, parent_text: str) -> Hit:
    hit = _hit(point_id, text)
    hit.payload.parent_index = parent_index
    hit.payload.parent_text = parent_text
    return hit


def test_rerank_keeps_only_the_best_child_of_each_parent() -> None:
    # Generation widens every hit to its parent window, so two children of one
    # parent would send the same text twice and waste the top_k budget.
    hits = [
        _child_hit("1", "child-a", 0, "window-0"),
        _child_hit("2", "child-b", 0, "window-0"),
        _child_hit("3", "child-c", 1, "window-1"),
    ]
    fake_scores = {"child-a": 0.4, "child-b": 0.9, "child-c": 0.5}

    def score_fn(_query: str, docs: list[str]) -> list[float]:
        return [next(v for k, v in fake_scores.items() if k in d) for d in docs]

    ranked = rerank("query", hits, top_k=5, score_fn=score_fn)
    assert [h.point_id for h in ranked] == ["2", "3"]


def test_rerank_collapse_frees_room_for_another_window() -> None:
    # Collapsing happens BEFORE the top_k cut, so top_k means top_k distinct
    # windows — a third parent still makes it into a top_k=2 result.
    hits = [
        _child_hit("1", "child-a", 0, "window-0"),
        _child_hit("2", "child-b", 0, "window-0"),
        _child_hit("3", "child-c", 1, "window-1"),
    ]
    fake_scores = {"child-a": 0.9, "child-b": 0.8, "child-c": 0.5}

    def score_fn(_query: str, docs: list[str]) -> list[float]:
        return [next(v for k, v in fake_scores.items() if k in d) for d in docs]

    ranked = rerank("query", hits, top_k=2, score_fn=score_fn)
    assert [h.point_id for h in ranked] == ["1", "3"]


def test_rerank_drops_hits_below_min_score() -> None:
    hits = [
        _hit("1", "chunk-irrelevant"),
        _hit("2", "chunk-rel"),
        _hit("3", "chunk-mid"),
    ]
    fake_scores = {"chunk-irrelevant": 0.05, "chunk-rel": 0.9, "chunk-mid": 0.3}

    def score_fn(_query: str, docs: list[str]) -> list[float]:
        return [next(v for k, v in fake_scores.items() if k in d) for d in docs]

    ranked = rerank("query", hits, top_k=5, min_score=0.2, score_fn=score_fn)
    assert [h.point_id for h in ranked] == ["2", "3"]


def test_rerank_returns_empty_when_nothing_clears_min_score() -> None:
    # The deterministic-refusal path in the chat endpoint depends on this:
    # all-irrelevant retrieval must yield [] rather than "the best of the bad".
    hits = [_hit("1", "a"), _hit("2", "b")]
    ranked = rerank(
        "query", hits, top_k=5, min_score=0.2, score_fn=lambda _q, d: [0.1] * len(d)
    )
    assert ranked == []


def test_rerank_min_score_zero_disables_the_floor() -> None:
    hits = [_hit("1", "a"), _hit("2", "b")]
    ranked = rerank(
        "query", hits, top_k=5, min_score=0.0, score_fn=lambda _q, d: [0.01, 0.02]
    )
    assert len(ranked) == 2


def test_rerank_relative_floor_drops_weak_cross_doc_chunk() -> None:
    # A strong top hit (0.9) with a weak tangential chunk (0.2): min_ratio=0.35
    # sets a relative floor of 0.315, dropping the weak chunk even though it
    # clears the absolute floor — the cross-document-leak guard.
    hits = [_hit("1", "strong"), _hit("2", "weak"), _hit("3", "mid")]
    fake_scores = {"strong": 0.9, "weak": 0.2, "mid": 0.5}

    def score_fn(_query: str, docs: list[str]) -> list[float]:
        return [next(v for k, v in fake_scores.items() if k in d) for d in docs]

    ranked = rerank(
        "query", hits, top_k=5, min_score=0.05, min_ratio=0.35, score_fn=score_fn
    )
    assert [h.point_id for h in ranked] == ["1", "3"]  # "weak" (0.2 < 0.315) dropped


def test_rerank_relative_floor_zero_is_noop() -> None:
    # min_ratio=0 (the default) keeps the pure absolute-floor behavior.
    hits = [_hit("1", "strong"), _hit("2", "weak")]
    fake_scores = {"strong": 0.9, "weak": 0.2}

    def score_fn(_query: str, docs: list[str]) -> list[float]:
        return [next(v for k, v in fake_scores.items() if k in d) for d in docs]

    ranked = rerank(
        "query", hits, top_k=5, min_score=0.05, min_ratio=0.0, score_fn=score_fn
    )
    assert [h.point_id for h in ranked] == ["1", "2"]


def test_rerank_candidates_truncates_before_scoring() -> None:
    # Hits arrive RRF-sorted; only the first ``candidates`` should reach the
    # cross-encoder. A later hit that would have scored highest must not win.
    hits = [_hit("1", "a"), _hit("2", "b"), _hit("3", "c"), _hit("4", "d")]
    seen: list[int] = []

    def score_fn(_query: str, docs: list[str]) -> list[float]:
        seen.append(len(docs))
        # Prefer later docs if they were scored — proves truncation works.
        return [0.1 + 0.1 * i for i in range(len(docs))]

    ranked = rerank(
        "query",
        hits,
        top_k=5,
        candidates=2,
        min_score=0.0,
        score_fn=score_fn,
    )
    assert seen == [2]
    assert [h.point_id for h in ranked] == ["2", "1"]


# --------------------------------------------------------------------------- #
# Product-scope guard (refuse when the named product isn't in the retrieved
# docs, instead of answering from a different product's benefit clauses)
# --------------------------------------------------------------------------- #


def test_product_guard_refuses_when_named_product_is_a_different_indexed_one() -> None:
    # Query names An Khang (a product the index contains) but only a DIFFERENT
    # indexed product was retrieved -> refuse rather than answer from the wrong
    # product's near-identical benefit clauses.
    known = [
        "Bảo hiểm liên kết chung An Khang Như Ý",
        "Bảo hiểm hỗn hợp An Lộc Vững Bền",
    ]
    hits = ["Bảo hiểm hỗn hợp An Lộc Vững Bền"]
    assert query_names_absent_product(
        "quyền lợi của bảo hiểm an khang như ý", hits, known_titles=known
    )


def test_product_guard_no_longer_refuses_a_product_absent_from_the_index() -> None:
    # CONTRACT (C1 fix): the guard used to invent a product from any noun after a
    # cue phrase, which false-refused ordinary questions. It now fires only for
    # products the index actually contains, so a product absent from the whole
    # corpus (deleted / not yet ingested) is left to the system prompt's rule-1
    # wrong-product refusal rather than a deterministic block here.
    known = ["Bảo hiểm liên kết chung An Khang Như Ý"]
    assert not query_names_absent_product(
        "quyền lợi của bảo hiểm An Thịnh Phúc Niên", known, known_titles=known
    )


def test_product_guard_allows_when_named_product_present() -> None:
    known = ["Bảo hiểm liên kết chung An Khang Như Ý"]
    assert not query_names_absent_product(
        "quyền lợi của bảo hiểm an khang như ý", known, known_titles=known
    )


def test_product_guard_ignores_generic_questions() -> None:
    # No specific product is named -> never blocks the general/topical question.
    titles = ["Bảo hiểm liên kết chung An Khang Như Ý"]
    assert not query_names_absent_product(
        "bảo hiểm nhân thọ là gì", titles, known_titles=titles
    )
    assert not query_names_absent_product(
        "bảo hiểm hỗn hợp gồm những gì", titles, known_titles=titles
    )
    assert not query_names_absent_product(
        "quyền lợi tử vong là gì", titles, known_titles=titles
    )


def test_product_guard_ignores_common_nouns_after_a_cue_phrase() -> None:
    # Regression (C1): the earlier guard read the noun after "bảo hiểm/sản phẩm"
    # as a product name, so ordinary questions fabricated a product ("bước",
    # "giấy tờ", "lâu") absent from every title and hard-refused. A common noun
    # does not strongly match any product title, so it must never refuse when the
    # relevant document was actually retrieved.
    known = [
        "Quy trình Giải quyết Quyền lợi Bảo hiểm (bản giả định)",
        "Quy tắc, Điều khoản Sản phẩm Bảo hiểm tử vong và thương tật nghiêm trọng",
        "Hướng dẫn Tính Dự phòng Toán học (tài liệu nội bộ giả định)",
        "Bảo hiểm liên kết chung An Khang Như Ý",
    ]
    process = ["Quy trình Giải quyết Quyền lợi Bảo hiểm (bản giả định)"]
    policy = [
        "Quy tắc, Điều khoản Sản phẩm Bảo hiểm tử vong và thương tật nghiêm trọng"
    ]
    reserve = ["Hướng dẫn Tính Dự phòng Toán học (tài liệu nội bộ giả định)"]
    cases = [
        ("Quy trình giải quyết quyền lợi bảo hiểm gồm những bước nào?", process),
        ("Hồ sơ yêu cầu giải quyết quyền lợi bảo hiểm gồm những giấy tờ gì?", process),
        (
            "Thời gian cân nhắc được quy định thế nào trong quy tắc, "
            "điều khoản sản phẩm?",
            policy,
        ),
        (
            "Dự phòng toán học theo phương pháp phí thuần cho hợp đồng bảo hiểm "
            "trọn đời được tính thế nào?",
            reserve,
        ),
        ("Thời gian chờ của hợp đồng bảo hiểm là bao lâu?", policy),
    ]
    for query, hits in cases:
        assert not query_names_absent_product(query, hits, known_titles=known), query


def test_product_guard_ignores_our_own_company_name() -> None:
    # Regression: "sản phẩm bảo hiểm của Bảo Việt Life" parsed "Việt Life" as a
    # product name, matched no document title, and hard-refused an answerable
    # question before generation ever ran. The company is not a product.
    titles = ["Bảo hiểm liên kết chung An Khang Như Ý", "Bảo hiểm hỗn hợp An Lộc"]
    for query in (
        "so sánh các sản phẩm bảo hiểm của bảo việt life và các công ty khác",
        "sản phẩm bảo hiểm của Bảo Việt Nhân Thọ có những gì?",
        "bảo việt life có những sản phẩm nào",
        "san pham bao hiem cua bao viet life",  # no diacritics
    ):
        assert not query_names_absent_product(query, titles, known_titles=titles), query


def test_product_guard_does_not_cross_a_clause_boundary() -> None:
    # A cue phrase must not skip past "và" and claim the next noun as a
    # product ("... và các công ty khác" is not a product name).
    from app.retrieval.product_scope import _fold_tokens, _product_spans

    spans = _product_spans(
        _fold_tokens("so sánh sản phẩm bảo hiểm của chúng ta và các công ty khác")
    )
    assert all("cong" not in span for span in spans)


def test_product_guard_absent_product_with_company_self_reference() -> None:
    # Under the C1 title-resolution contract a product absent from the index is
    # no longer deterministically refused (see
    # test_product_guard_no_longer_refuses_a_product_absent_from_the_index); the
    # system prompt's rule 1 handles the wrong-product case instead. The company
    # self-reference must still not be parsed as a product either way.
    known = ["Bảo hiểm liên kết chung An Khang Như Ý"]
    assert not query_names_absent_product(
        "quyền lợi của bảo hiểm An Thịnh Phúc Niên của Bảo Việt Life",
        known,
        known_titles=known,
    )


def test_product_guard_matches_without_diacritics() -> None:
    known = [
        "SẢN PHẨM BẢO HIỂM HỖN HỢP Lộc Vững Bền",
        "Bảo hiểm liên kết chung An Khang Như Ý",
    ]
    loc = ["SẢN PHẨM BẢO HIỂM HỖN HỢP Lộc Vững Bền"]
    # No-diacritics typing still lines up with the diacritic title (present).
    assert not query_names_absent_product(
        "bao hiem loc vung ben co quyen loi gi", loc, known_titles=known
    )
    # Names a different indexed product (An Khang) with no diacritics while only
    # Lộc Vững Bền was retrieved -> refuse.
    assert query_names_absent_product(
        "bao hiem an khang nhu y co quyen loi gi", loc, known_titles=known
    )


def test_named_product_labels_extracts_both_comparison_products() -> None:
    from app.retrieval.product_scope import named_product_labels

    q = (
        "So sánh quyền lợi tử vong của bảo hiểm hỗn hợp An Lộc Vững Bền "
        "và bảo hiểm liên kết chung An Khang Như Ý"
    )
    labels = named_product_labels(q, titles=[])
    assert len(labels) >= 2
    joined = " ".join(labels).lower()
    assert "lộc" in joined or "loc" in joined.lower()
    assert "khang" in joined.lower()


def test_informal_nicknames_resolve_via_indexed_titles() -> None:
    from app.retrieval.comparison import is_multi_product_query
    from app.retrieval.product_scope import mentioned_doc_titles, named_product_labels

    titles = [
        "Bảo hiểm liên kết chung An Khang Như Ý",
        "Bảo hiểm hỗn hợp An Lộc Vững Bền",
    ]
    q = (
        "so sánh quyền lợi cầu an khang như ý và an lộc vững bền. "
        "KH sẽ thích sản phẩm nào hơn?"
    )
    mentioned = mentioned_doc_titles(q, titles)
    assert len(mentioned) == 2
    labels = named_product_labels(q, titles=titles)
    assert labels == mentioned
    assert is_multi_product_query(q, titles=titles)


def test_product_guard_allows_partial_comparison_hit() -> None:
    # Comparison names A and B; only A was retrieved → do NOT refuse (generation
    # can still answer A and say B is missing). Refuse only when neither hits.
    known = [
        "Bảo hiểm hỗn hợp An Lộc Vững Bền",
        "Bảo hiểm liên kết chung An Khang Như Ý",
    ]
    q = (
        "so sánh bảo hiểm hỗn hợp An Lộc Vững Bền và "
        "bảo hiểm liên kết chung An Khang Như Ý"
    )
    assert not query_names_absent_product(
        q, ["Bảo hiểm hỗn hợp An Lộc Vững Bền"], known_titles=known
    )
    assert query_names_absent_product(q, ["Từ điển thuật ngữ"], known_titles=known)


# --------------------------------------------------------------------------- #
# Comparison / multi-product retrieval (per-product quota + merge)
# --------------------------------------------------------------------------- #


def _cmp_hit(pid: str, title: str, section: str = "QL") -> Hit:
    return Hit(
        point_id=pid,
        score=1.0,
        payload=QdrantPayload(
            doc_id=f"d-{pid}",
            doc_title=title,
            section_path=section,
            doc_type=DocType.POLICY,
            display_text=f"nội dung {section}",
            chunk_index=0,
            ingested_at="2026-01-01T00:00:00+00:00",
        ),
    )


def test_merge_per_product_hits_round_robins_and_dedupes() -> None:
    from app.retrieval.comparison import merge_per_product_hits

    a = [_cmp_hit("a1", "A"), _cmp_hit("a2", "A"), _cmp_hit("shared", "A")]
    b = [_cmp_hit("b1", "B"), _cmp_hit("shared", "B"), _cmp_hit("b2", "B")]
    merged = merge_per_product_hits([a, b], total_cap=4)
    assert [h.point_id for h in merged] == ["a1", "b1", "a2", "shared"]


def test_retrieve_multi_product_quotas_each_side() -> None:
    from app.retrieval.comparison import retrieve_multi_product

    akny = "Bảo hiểm liên kết chung An Khang Như Ý"
    alvb = "Bảo hiểm hỗn hợp An Lộc Vững Bền"
    # Search returns the same mixed pool every time; title filter + quota should
    # still keep both products in the merged context.
    pool = [
        _cmp_hit("k1", akny, "Tử vong"),
        _cmp_hit("k2", akny, "Chú thích"),
        _cmp_hit("k3", akny, "TT cần biết"),
        _cmp_hit("k4", akny, "Giới thiệu"),
        _cmp_hit("l1", alvb, "QL sản phẩm"),
        _cmp_hit("l2", alvb, "TTTV"),
    ]

    def search_fn(_q: str, _doc_ids: list[str] | None) -> list[Hit]:
        return list(pool)

    def rerank_fn(_q: str, hits: list[Hit], top_k: int) -> list[Hit]:
        return hits[:top_k]

    q = (
        "So sánh quyền lợi tử vong và thương tật của "
        "bảo hiểm hỗn hợp An Lộc Vững Bền và bảo hiểm liên kết chung An Khang Như Ý"
    )
    out = retrieve_multi_product(
        q,
        search_fn=search_fn,
        rerank_fn=rerank_fn,
        per_product_top_k=2,
        max_products=2,
        titles=[akny, alvb],
        docs=[],
    )
    titles = {h.payload.doc_title for h in out}
    assert akny in titles
    assert alvb in titles
    assert len(out) == 4  # 2 per product


def test_retrieve_multi_product_scopes_search_by_doc_id() -> None:
    """Each product's search is filtered to its own documents."""
    from app.retrieval.comparison import retrieve_multi_product

    akny = "Bảo hiểm liên kết chung An Khang Như Ý"
    alvb = "Bảo hiểm hỗn hợp An Lộc Vững Bền"
    docs = [("doc-akny", akny), ("doc-alvb", alvb)]
    seen: list[list[str] | None] = []

    def search_fn(_q: str, doc_ids: list[str] | None) -> list[Hit]:
        seen.append(doc_ids)
        return [_cmp_hit("h1", akny if doc_ids == ["doc-akny"] else alvb)]

    def rerank_fn(_q: str, hits: list[Hit], top_k: int) -> list[Hit]:
        return hits[:top_k]

    retrieve_multi_product(
        "so sánh quyền lợi của An Khang Như Ý và An Lộc Vững Bền",
        search_fn=search_fn,
        rerank_fn=rerank_fn,
        per_product_top_k=2,
        max_products=2,
        titles=[akny, alvb],
        docs=docs,
    )
    assert sorted(ids[0] for ids in seen if ids) == ["doc-akny", "doc-alvb"]


def test_retrieve_multi_product_keeps_low_ranked_benefit_chunk() -> None:
    """Regression: title filtering must precede the rerank top-k cut.

    The old order (rerank to a global top-k, then filter by title) let the
    better-parsed product fill the cut, so the other product kept only its
    cover-page chunks and the model answered "không nêu rõ" for indexed facts.
    """
    from app.retrieval.comparison import retrieve_multi_product

    akny = "Bảo hiểm liên kết chung An Khang Như Ý"
    alvb = "Bảo hiểm hỗn hợp An Lộc Vững Bền"
    # AKNY's real benefit section sits below many ALVB chunks in the raw pool.
    pool = [
        _cmp_hit("k-cover", akny, "THÔNG TIN CẦN BIẾT"),
        *[_cmp_hit(f"l{i}", alvb, "QUYỀN LỢI SẢN PHẨM") for i in range(8)],
        _cmp_hit("k-benefit", akny, "QUYỀN LỢI BẢO HIỂM"),
    ]

    def search_fn(_q: str, _doc_ids: list[str] | None) -> list[Hit]:
        return list(pool)

    def rerank_fn(_q: str, hits: list[Hit], top_k: int) -> list[Hit]:
        return hits[:top_k]  # order-preserving stand-in for the cross-encoder

    out = retrieve_multi_product(
        "so sánh quyền lợi của An Khang Như Ý và An Lộc Vững Bền",
        search_fn=search_fn,
        rerank_fn=rerank_fn,
        per_product_top_k=2,
        max_products=2,
        titles=[akny, alvb],
        docs=[],
    )
    assert "k-benefit" in {h.point_id for h in out}


def test_build_filter_matches_any_for_list_values() -> None:
    from app.retrieval.retriever import _build_filter

    f = _build_filter({"doc_id": ["a", "b"], "doc_type": "policy"})
    assert f is not None
    matches = {c.key: c.match for c in f.must}
    assert matches["doc_id"].any == ["a", "b"]
    assert matches["doc_type"].value == "policy"


def test_is_multi_product_query() -> None:
    from app.retrieval.comparison import is_multi_product_query

    assert is_multi_product_query(
        "so sánh bảo hiểm An Lộc Vững Bền và bảo hiểm An Khang Như Ý",
        titles=[],
    )
    assert not is_multi_product_query("quyền lợi bảo hiểm An Khang Như Ý", titles=[])


def test_is_multi_product_query_ignores_junk_second_span() -> None:
    # Regression (H6): an open-ended "A so với sản phẩm nào trên thị trường?"
    # extracts one real product + a junk span. With the indexed titles known,
    # the junk span resolves to no product, so this must NOT route to comparison
    # (which would burn a full search+rerank pass on the junk label).
    from app.retrieval.comparison import is_multi_product_query

    titles = [
        "Bảo hiểm liên kết chung An Khang Như Ý",
        "Bảo hiểm hỗn hợp An Lộc Vững Bền",
    ]
    assert not is_multi_product_query(
        "bảo hiểm An Khang Như Ý so với sản phẩm nào trên thị trường không?",
        titles=titles,
    )
    # A genuine two-product comparison still routes to multi.
    assert is_multi_product_query(
        "so sánh An Khang Như Ý và An Lộc Vững Bền", titles=titles
    )


def test_retrieve_multi_product_skips_junk_label_pass() -> None:
    # Regression (H6): a junk label that matches no indexed document must not get
    # its own search+rerank pass (each costs ~tens of seconds on CPU).
    from app.retrieval.comparison import retrieve_multi_product

    akny = "Bảo hiểm liên kết chung An Khang Như Ý"
    alvb = "Bảo hiểm hỗn hợp An Lộc Vững Bền"
    docs = [("doc-akny", akny), ("doc-alvb", alvb)]
    searched: list[str] = []

    def search_fn(_q: str, doc_ids: list[str] | None) -> list[Hit]:
        searched.append(doc_ids[0] if doc_ids else "UNSCOPED")
        title = akny if doc_ids == ["doc-akny"] else alvb
        return [_cmp_hit("h", title)]

    def rerank_fn(_q: str, hits: list[Hit], top_k: int) -> list[Hit]:
        return hits[:top_k]

    retrieve_multi_product(
        "so sánh quyền lợi",  # query text irrelevant; labels are injected
        search_fn=search_fn,
        rerank_fn=rerank_fn,
        per_product_top_k=2,
        max_products=3,
        docs=docs,
        labels=[akny, "không", alvb],  # middle label is junk
    )
    # Only the two real products get a pass; "không" is dropped, not searched.
    assert sorted(searched) == ["doc-akny", "doc-alvb"]


# --------------------------------------------------------------------------- #
# Metric guard (drop fee/interest tables from benefit-payout queries)
# --------------------------------------------------------------------------- #


def _metric_hit(section: str, text: str) -> Hit:
    return Hit(
        point_id="p",
        score=1.0,
        payload=QdrantPayload(
            doc_id="d",
            doc_title="An Phú Liên Kết",
            section_path=section,
            doc_type=DocType.POLICY,
            display_text=text,
            chunk_index=0,
            ingested_at="2026-01-01T00:00:00+00:00",
        ),
    )


def test_metric_guard_detects_claim_percent_query() -> None:
    from app.retrieval.metric_guard import is_benefit_payout_query

    assert is_benefit_payout_query(
        "nếu tôi gặp tai nạn xe cộ và chết thì được claim bao nhiêu%?"
    )
    assert not is_benefit_payout_query(
        "Lãi suất cam kết tối thiểu năm 1 của An Phú Liên Kết là bao nhiêu?"
    )


def test_metric_guard_drops_interest_table_from_claim_query() -> None:
    from app.retrieval.metric_guard import filter_metric_mismatch

    interest = _metric_hit(
        "Chương II > Điều 4",
        "Lãi suất cam kết tối thiểu:\n\n| Năm | % |\n| --- | --- |\n| 1 | 2.5 |",
    )
    benefit = _metric_hit(
        "Chương I > Điều 1",
        "Chi trả 100% Số tiền bảo hiểm nếu tử vong do tai nạn.",
    )
    q = "gặp tai nạn xe cộ và chết thì được claim bao nhiêu%?"
    out = filter_metric_mismatch(q, [interest, benefit])
    assert len(out) == 1
    assert out[0].payload.section_path == "Chương I > Điều 1"


def test_metric_guard_empties_when_only_interest_hits_remain() -> None:
    from app.retrieval.metric_guard import filter_metric_mismatch

    interest = _metric_hit(
        "Điều 4: Lãi suất cam kết tối thiểu",
        "| Năm hợp đồng | Lãi suất cam kết tối thiểu (%) |\n| --- | --- |\n| 1 | 2.5 |",
    )
    q = "chết vì tai nạn thì claim bao nhiêu%?"
    assert filter_metric_mismatch(q, [interest]) == []


def test_metric_guard_noop_for_interest_rate_question() -> None:
    from app.retrieval.metric_guard import filter_metric_mismatch

    interest = _metric_hit(
        "Điều 4",
        "Lãi suất cam kết tối thiểu năm 1 là 2.5%.",
    )
    q = "Lãi suất cam kết tối thiểu năm 1 là bao nhiêu?"
    assert filter_metric_mismatch(q, [interest]) == [interest]


def test_metric_guard_sees_the_parent_window_of_a_child_chunk() -> None:
    # Under parent-child chunking the caption naming the metric can sit in the
    # parent while the matched child is a bare row group. The guard must judge
    # the text generation would receive, not just the child.
    from app.retrieval.metric_guard import filter_metric_mismatch

    child = _metric_hit("Chương II > Điều 4", "| Năm | % |\n| --- | --- |\n| 1 | 2.5 |")
    child.payload.parent_index = 0
    child.payload.parent_text = (
        "Lãi suất cam kết tối thiểu theo năm hợp đồng:\n\n"
        "| Năm | % |\n| --- | --- |\n| 1 | 2.5 |"
    )
    q = "gặp tai nạn xe cộ và chết thì được claim bao nhiêu%?"
    assert filter_metric_mismatch(q, [child]) == []
