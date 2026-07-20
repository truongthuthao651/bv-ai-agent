"""Tests for pure request-routing helpers in app/api/chat.py.

No Qdrant/Ollama/FastAPI client needed: _resolve_confirmation is a pure function
over the message list, exercising the stateful spellcheck-confirmation flow.
"""

from __future__ import annotations

from app.api.chat import _resolve_confirmation
from app.models.schemas import ChatMessage
from app.retrieval.spellcheck import build_confirmation_message
from app.retrieval.spellcheck import Suggestion

_CLARIFICATION = build_confirmation_message(
    [
        Suggestion(canonical="bảo hiểm trọn đời", matched_span="x", ratio=0.9),
        Suggestion(
            canonical="Sản phẩm Bảo hiểm tử vong và thương tật nghiêm trọng do tai nạn",
            matched_span="y",
            ratio=0.9,
        ),
    ]
)
_ORIGINAL = "Liệt kê chi tiết các quyền lợi của Sản phẩm Bảo hiểm tử vong ..."


def test_confirmation_replays_original_question_and_skips_gate() -> None:
    history = [
        ChatMessage(role="user", content=_ORIGINAL),
        ChatMessage(role="assistant", content=_CLARIFICATION),
    ]
    query, new_history, skip = _resolve_confirmation("đúng", history)
    assert query == _ORIGINAL  # not the bare "đúng"
    assert skip is True  # gate bypassed so it can't re-trigger
    assert new_history == []  # resolved exchange dropped from history


def test_non_affirmation_reply_is_left_untouched() -> None:
    history = [
        ChatMessage(role="user", content=_ORIGINAL),
        ChatMessage(role="assistant", content=_CLARIFICATION),
    ]
    query, new_history, skip = _resolve_confirmation("còn phí thì sao", history)
    assert query == "còn phí thì sao"
    assert skip is False
    assert new_history == history


def test_affirmation_without_prior_clarification_is_untouched() -> None:
    # "đúng" following an ordinary answer is not a spellcheck confirmation.
    history = [
        ChatMessage(role="user", content=_ORIGINAL),
        ChatMessage(role="assistant", content="Quyền lợi gồm..."),
    ]
    query, new_history, skip = _resolve_confirmation("đúng", history)
    assert query == "đúng"
    assert skip is False
    assert new_history == history
