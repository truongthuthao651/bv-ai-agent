"""Tests for pure request-routing helpers in app/api/chat.py.

No Qdrant/Ollama/FastAPI client needed: _resolve_confirmation is a pure function
over the message list, exercising the stateful spellcheck-confirmation flow.
"""

from __future__ import annotations

from app.api.chat import _resolve_confirmation
from app.generation.prompts import REFUSAL_MESSAGE
from app.models.schemas import ChatMessage
from app.retrieval.conversation_scope import active_scope
from app.retrieval.spellcheck import Suggestion, build_confirmation_message

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
_AKNY = "Bảo hiểm liên kết chung An Khang Như Ý"
_ANSWER_WITH_SOURCES = (
    f"Quyền lợi gồm...\n\n**Nguồn tham khảo:**\n"
    f"- [1] [{_AKNY}](http://localhost/documents/d1/view) — Điều 5"
)


def test_confirmation_replays_original_question_and_skips_gate() -> None:
    history = [
        ChatMessage(role="user", content=_ORIGINAL),
        ChatMessage(role="assistant", content=_CLARIFICATION),
    ]
    query, new_history, skip = _resolve_confirmation("đúng", history)
    # Affirmation replays the prior user turn (possibly with spellcheck
    # substitutions applied); gate is skipped so it can't re-trigger.
    assert "quyền lợi" in query.lower() or "Bảo hiểm" in query
    assert skip is True
    assert new_history == []  # resolved exchange dropped from history


def test_confirmation_applies_suggested_canonical_name() -> None:
    from app.retrieval.spellcheck import (
        Suggestion,
        apply_suggestions,
        build_confirmation_message,
    )

    original = "so sánh an loc vuwng ben và an khang như ý"
    suggestions = [
        Suggestion(
            canonical="Bảo hiểm hỗn hợp An Lộc Vững Bền",
            matched_span="an loc vuwng ben",
            ratio=0.9,
        )
    ]
    prompt = build_confirmation_message(suggestions)
    history = [
        ChatMessage(role="user", content=original),
        ChatMessage(role="assistant", content=prompt),
    ]
    # apply_suggestions is the pure step; confirmation re-runs find_suggestions
    # against the live corpus, so assert the helper here and that affirmation
    # still routes off the bare "đúng".
    assert "Bảo hiểm hỗn hợp An Lộc Vững Bền" in apply_suggestions(
        original, suggestions
    )
    query, new_history, skip = _resolve_confirmation("đúng", history)
    assert skip is True
    assert query != "đúng"
    assert new_history == []


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


def test_scoped_follow_up_detects_prior_cited_document() -> None:
    # Chat endpoint uses active_scope(history) to skip hybrid fallback on
    # company-document follow-ups that retrieve nothing.
    history = [
        ChatMessage(role="user", content="Quyền lợi An Khang Như Ý?"),
        ChatMessage(role="assistant", content=_ANSWER_WITH_SOURCES),
    ]
    assert active_scope(history) == _AKNY


# --------------------------------------------------------------------------- #
# Answer-mode routing through the endpoint
# --------------------------------------------------------------------------- #


def _stub_hit():
    from app.models.schemas import DocType, Hit, QdrantPayload

    return Hit(
        point_id="p1",
        score=0.9,
        payload=QdrantPayload(
            doc_id="d1",
            doc_title=_AKNY,
            section_path="Điều 5",
            doc_type=DocType.POLICY,
            display_text="Quyền lợi tử vong: 100% STBH.",
            chunk_index=0,
            ingested_at="2026-01-01T00:00:00+00:00",
        ),
    )


def _post(monkeypatch, query: str, history: list[ChatMessage]) -> bool:
    """Send one non-streaming turn; return whether the advisory prompt was used.

    Retrieval and Ollama are stubbed out — this pins the endpoint's *routing*,
    which is the part that decides whether a comparison follow-up gets refused.
    """
    from fastapi.testclient import TestClient

    from app.api import chat as chat_module
    from app.generation import generator
    from app.generation.prompts import system_prompt
    from app.main import app

    monkeypatch.setattr(
        chat_module,
        "_retrieve",
        lambda q, h: (q, [_stub_hit()], chat_module._advisory_followup_labels(q, h)),
    )
    seen: dict[str, str] = {}

    def fake_generate_chat(messages, suffix_fn):
        seen["system"] = messages[0]["content"]
        return "Câu trả lời."

    monkeypatch.setattr(generator, "_generate_chat", fake_generate_chat)

    body = {
        "messages": [m.model_dump() for m in history]
        + [{"role": "user", "content": query}],
        "stream": False,
    }
    resp = TestClient(app).post("/v1/chat/completions", json=body)
    assert resp.status_code == 200, resp.text
    return seen["system"] == system_prompt(advisory=True)


def test_advisory_question_routes_to_the_advisory_prompt(monkeypatch) -> None:
    history = [
        ChatMessage(role="user", content="Quyền lợi An Khang Như Ý?"),
        ChatMessage(role="assistant", content=_ANSWER_WITH_SOURCES),
    ]
    assert _post(monkeypatch, "khách hàng nên chọn sản phẩm nào?", history) is True


def test_lookup_question_stays_on_the_strict_prompt(monkeypatch) -> None:
    assert _post(monkeypatch, "quyền lợi tử vong là bao nhiêu?", []) is False


def test_advisory_mode_can_be_disabled(monkeypatch) -> None:
    from app.config import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "advisory_mode_enabled", False)
    assert _post(monkeypatch, "khách hàng nên chọn sản phẩm nào?", []) is False


def test_company_self_reference_is_not_refused_by_the_product_guard(
    monkeypatch,
) -> None:
    # Regression: asking about "sản phẩm bảo hiểm của Bảo Việt Life" was parsed
    # as naming a product no document covers, so the endpoint returned the
    # refusal sentence before generation ran. It must now answer (advisory).
    from fastapi.testclient import TestClient

    from app.api import chat as chat_module
    from app.generation import generator
    from app.main import app

    monkeypatch.setattr(chat_module, "_retrieve", lambda q, h: (q, [_stub_hit()], []))
    monkeypatch.setattr(
        generator, "_generate_chat", lambda messages, suffix_fn: "Câu trả lời."
    )
    body = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "so sánh các sản phẩm bảo hiểm của bảo việt life "
                    "và các công ty khác"
                ),
            }
        ],
        "stream": False,
    }
    resp = TestClient(app).post("/v1/chat/completions", json=body)
    assert resp.status_code == 200
    content = resp.json()["choices"][0]["message"]["content"]
    assert content != REFUSAL_MESSAGE
    assert "Câu trả lời." in content
