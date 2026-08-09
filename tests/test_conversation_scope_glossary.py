"""Scope and rewrite guards when glossary citations precede product questions."""

from __future__ import annotations

from app.models.schemas import ChatMessage
from app.retrieval.conversation_scope import (
    _scope_from_citations,
    active_scope,
    ensure_prior_topic,
)
from app.retrieval.product_scope import is_glossary_title, is_product_summary_query
from app.retrieval.spellcheck import find_fuzzy_product_titles, maybe_suggest_correction

_GLOSSARY = "Từ điển thuật ngữ định phí bảo hiểm"
_ATHD = "Bảo hiểm Liên kết chung An Tâm Hoạch Định"


def test_is_glossary_title() -> None:
    assert is_glossary_title(_GLOSSARY)
    assert not is_glossary_title(_ATHD)


def test_scope_from_citations_skips_glossary_only() -> None:
    history = [
        ChatMessage(
            role="assistant",
            content=f"Phí thuần là…\n\n**Nguồn tham khảo:**\n- [1] [{_GLOSSARY}](/x) — mục",
        )
    ]
    assert _scope_from_citations(history) is None


def test_active_scope_prefers_product_in_current_query_over_glossary_citations(
    monkeypatch,
) -> None:
    import app.retrieval.product_scope as ps

    monkeypatch.setattr(ps, "_load_indexed_titles", lambda: [_GLOSSARY, _ATHD])
    history = [
        ChatMessage(role="user", content="phí thuần là gì"),
        ChatMessage(
            role="assistant",
            content=f"…\n\n**Nguồn tham khảo:**\n- [1] [{_GLOSSARY}](/x) — mục",
        ),
    ]
    scope = active_scope(history, current_query="tóm tắt bảo hiểm an tâm hoạch định")
    assert scope == _ATHD


def test_ensure_prior_topic_skips_when_product_named(monkeypatch) -> None:
    import app.retrieval.product_scope as ps

    monkeypatch.setattr(ps, "_load_indexed_titles", lambda: [_GLOSSARY, _ATHD])
    history = [ChatMessage(role="user", content="phí thuần là gì")]
    q = "bảo hiểm an tâm hoạch định"
    assert ensure_prior_topic(q, history) == q


def test_is_product_summary_includes_chi_tiet() -> None:
    assert is_product_summary_query("tóm tắt chi tiết bảo hiểm an tâm hoạch định")


def test_fuzzy_product_title_match_on_garbled_summary_request() -> None:
    titles = [_GLOSSARY, _ATHD]
    q = "tóm tắt chi tiết bao hiemm an tam hoach dinh"
    matched = find_fuzzy_product_titles(q, titles)
    assert _ATHD in matched


def test_spellcheck_auto_passes_garbled_product_summary(monkeypatch) -> None:
    import app.retrieval.spellcheck as sc

    monkeypatch.setattr(
        sc, "_indexed_corpus", lambda: ([_GLOSSARY, _ATHD], frozenset())
    )
    q = "tóm tắt chi tiết bao hiemm an tam hoach dinh"
    assert maybe_suggest_correction(q) is None
