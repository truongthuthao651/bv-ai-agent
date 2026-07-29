"""Second-pass verifier: parsing, fail-open behaviour, and the correction turn.

The verifier exists for the two failures the deterministic gate cannot see,
both observed in production on 2026-07-27: the answer asserted the customer
had been "đua xe" when the question said an ordinary car accident, and it
quoted a clause paying out "không phụ thuộc nguyên nhân" before concluding the
event was not covered.

No Ollama here — the HTTP call is stubbed. What matters is that a rejection is
routed to the right correction and that EVERY failure path passes the answer
through rather than blocking it.
"""

from __future__ import annotations

import httpx
import pytest

from app.generation import verify
from app.generation.verify import verification_messages, verify_answer


def _stub_response(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    """Make the verifier's Ollama call return ``payload`` as its JSON body."""

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return payload

    monkeypatch.setattr(verify.httpx, "post", lambda *a, **kw: _Resp())


def test_clean_answer_produces_no_correction(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_response(
        monkeypatch,
        {"response": '{"them_tinh_tiet": false, "nguoc_trich_dan": false}'},
    )
    assert verify_answer("tai nạn xe tử vong", "Theo [2] được chi trả.") is None


def test_invented_facts_are_reported_with_the_right_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The observed case: "tai nạn xe" asserted as "đua xe"."""
    _stub_response(
        monkeypatch,
        {"response": '{"them_tinh_tiet": true, "nguoc_trich_dan": false}'},
    )
    reason = verify_answer("bị tai nạn xe", "người bị tai nạn là đua xe...")
    assert reason is not None
    assert "không hề nêu" in reason


def test_contradicting_its_own_citation_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_response(
        monkeypatch,
        {"response": '{"them_tinh_tiet": false, "nguoc_trich_dan": true}'},
    )
    reason = verify_answer("tai nạn xe tử vong", "Trích [1] ... không thuộc quyền lợi")
    assert reason is not None
    assert "NGƯỢC với chính đoạn tài liệu" in reason


def test_verdict_json_embedded_in_prose_is_still_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_response(
        monkeypatch,
        {"response": 'Kết quả: {"them_tinh_tiet": true, "nguoc_trich_dan": false} .'},
    )
    assert verify_answer("q", "a") is not None


class TestFailsOpen:
    """A verifier that is down or confused must never block an answer."""

    def test_unparseable_output_passes_the_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_response(monkeypatch, {"response": "tôi không chắc"})
        assert verify_answer("q", "a") is None

    def test_transport_failure_passes_the_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*a: object, **kw: object) -> None:
            raise httpx.ConnectError("ollama down")

        monkeypatch.setattr(verify.httpx, "post", boom)
        assert verify_answer("q", "a") is None

    def test_empty_answer_is_not_sent_for_verification(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*a: object, **kw: object) -> None:
            raise AssertionError("must not call the model for an empty answer")

        monkeypatch.setattr(verify.httpx, "post", boom)
        assert verify_answer("q", "   ") is None

    def test_disabled_by_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(verify.settings, "coverage_llm_verify_enabled", False)

        def boom(*a: object, **kw: object) -> None:
            raise AssertionError("must not call the model when disabled")

        monkeypatch.setattr(verify.httpx, "post", boom)
        assert verify_answer("q", "a") is None


def test_verification_messages_replay_the_rejected_answer() -> None:
    base = [{"role": "system", "content": "..."}]
    out = verification_messages(base, "câu trả lời sai", "lý do")
    assert out[:1] == base
    assert out[-2] == {"role": "assistant", "content": "câu trả lời sai"}
    assert out[-1]["role"] == "user"
    assert "lý do" in out[-1]["content"]
    # The correction must not become the answer's outline (the leak we fixed).
    assert "KHÔNG nhắc lại" in out[-1]["content"]
