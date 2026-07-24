"""Advisory / synthesis routing tests.

Covers the deterministic query classifier, the carry-over of products under
comparison across turns, and the chat-endpoint helper that wires the two — all
pure, no Qdrant / Ollama.
"""

from __future__ import annotations

import pytest

from app.api.chat import _advisory_followup_labels
from app.generation.advisory import is_advisory_query
from app.models.schemas import ChatMessage
from app.retrieval.conversation_scope import cited_titles_in_history

# --------------------------------------------------------------------------- #
# Query classification
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "query",
    [
        # The turn that regressed in production: a comparison follow-up asking
        # for a conclusion no document states, refused by the strict prompt.
        "KH sẽ chọn sản phẩm nào nhỉ",
        "khách hàng nên chọn sản phẩm nào?",
        "sản phẩm nào phù hợp với khách hàng 30 tuổi?",
        "so sánh quyền lợi của An Khang Như Ý và An Lộc Vững Bền",
        "hai sản phẩm này khác nhau thế nào?",
        "ưu điểm của bảo hiểm liên kết chung là gì?",
        "nhược điểm của sản phẩm này?",
        "tư vấn giúp mình chọn gói bảo hiểm",
        "cái nào tốt hơn?",
        "đánh giá sản phẩm An Khang Như Ý",
        # Habitual no-diacritics typing must classify identically.
        "kh nen chon san pham nao",
        "so sanh quyen loi hai san pham",
    ],
)
def test_advisory_questions_are_detected(query: str) -> None:
    assert is_advisory_query(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "quyền lợi tử vong của An Khang Như Ý là bao nhiêu?",
        "phí bảo hiểm cơ bản tối thiểu là bao nhiêu?",
        "thời gian cân nhắc là mấy ngày?",
        "công thức tính phí thuần là gì?",
        "quy trình bồi thường gồm những bước nào?",
        "liệt kê các điều khoản loại trừ",
        "trích dẫn Điều 5 của quy tắc",
        "",
        "   ",
    ],
)
def test_lookup_questions_are_not_advisory(query: str) -> None:
    assert is_advisory_query(query) is False


def test_lookup_verb_does_not_suppress_a_strong_advisory_cue() -> None:
    # "liệt kê" alone is a lookup, but not when the turn also asks for a choice.
    assert is_advisory_query("liệt kê quyền lợi") is False
    assert is_advisory_query("liệt kê quyền lợi rồi tư vấn nên chọn cái nào") is True


# --------------------------------------------------------------------------- #
# Carrying the compared products across turns
# --------------------------------------------------------------------------- #


def _sources(*titles: str) -> str:
    """An assistant turn ending in the deterministic sources footer."""
    lines = [
        f"- [{i}] [{t}](http://localhost:8000/documents/d{i}/view) — Mục {i}"
        for i, t in enumerate(titles, start=1)
    ]
    return "Nội dung trả lời.\n\n**Nguồn tham khảo:**\n" + "\n".join(lines)


def test_cited_titles_in_history_collects_every_compared_product() -> None:
    history = [
        ChatMessage(role="user", content="so sánh A và B"),
        ChatMessage(
            role="assistant",
            content=_sources(
                "Bảo hiểm liên kết chung An Khang Như Ý",
                "Bảo hiểm hỗn hợp An Lộc Vững Bền",
                "Bảo hiểm liên kết chung An Khang Như Ý",  # repeat -> once
            ),
        ),
    ]
    assert cited_titles_in_history(history) == [
        "Bảo hiểm liên kết chung An Khang Như Ý",
        "Bảo hiểm hỗn hợp An Lộc Vững Bền",
    ]


def test_cited_titles_in_history_is_empty_without_citations() -> None:
    history = [
        ChatMessage(role="user", content="xin chào"),
        ChatMessage(role="assistant", content="Chào anh/chị."),
    ]
    assert cited_titles_in_history(history) == []


def test_advisory_followup_carries_the_products_under_comparison() -> None:
    # "KH sẽ chọn sản phẩm nào nhỉ" names no product: without carry-over the
    # sticky single-product scope pins one of the two and the other product's
    # benefits never reach the context.
    history = [
        ChatMessage(role="user", content="lập bảng so sánh quyền lợi A và B"),
        ChatMessage(
            role="assistant",
            content=_sources(
                "Bảo hiểm liên kết chung An Khang Như Ý",
                "Bảo hiểm hỗn hợp An Lộc Vững Bền",
            ),
        ),
    ]
    labels = _advisory_followup_labels("KH sẽ chọn sản phẩm nào nhỉ", history)
    assert labels == [
        "Bảo hiểm liên kết chung An Khang Như Ý",
        "Bảo hiểm hỗn hợp An Lộc Vững Bền",
    ]


def test_no_carry_over_for_a_plain_lookup_followup() -> None:
    history = [
        ChatMessage(role="user", content="so sánh A và B"),
        ChatMessage(
            role="assistant",
            content=_sources("Sản phẩm An Khang Như Ý", "Sản phẩm An Lộc Vững Bền"),
        ),
    ]
    assert _advisory_followup_labels("thời gian cân nhắc là mấy ngày?", history) == []


def test_no_carry_over_when_only_one_product_was_cited() -> None:
    history = [
        ChatMessage(role="user", content="quyền lợi của A?"),
        ChatMessage(role="assistant", content=_sources("Sản phẩm An Khang Như Ý")),
    ]
    assert _advisory_followup_labels("nên chọn sản phẩm nào?", history) == []


def test_no_carry_over_when_the_query_already_names_the_products() -> None:
    # The query text is the better signal; carry-over is only for turns that
    # name nothing themselves.
    history = [
        ChatMessage(role="user", content="so sánh A và B"),
        ChatMessage(
            role="assistant",
            content=_sources("Sản phẩm An Khang Như Ý", "Sản phẩm An Lộc Vững Bền"),
        ),
    ]
    query = "nên chọn bảo hiểm An Khang Như Ý hay bảo hiểm An Lộc Vững Bền?"
    assert _advisory_followup_labels(query, history) == []


def test_carry_over_disabled_by_settings(monkeypatch) -> None:
    from app.config import settings as settings_module

    history = [
        ChatMessage(role="user", content="so sánh A và B"),
        ChatMessage(
            role="assistant",
            content=_sources("Sản phẩm An Khang Như Ý", "Sản phẩm An Lộc Vững Bền"),
        ),
    ]
    monkeypatch.setattr(settings_module.settings, "advisory_mode_enabled", False)
    assert _advisory_followup_labels("KH sẽ chọn sản phẩm nào nhỉ", history) == []
