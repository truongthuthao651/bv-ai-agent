"""The finished coverage answer must have read the payout side before concluding.

Encodes the 2026-07-27 four-turn conversation on a real policy PDF. With the
benefit clause backfilled into context AND reordered to the front, the answer
still denied the claim in all four turns citing only the exclusions page —
"QUYỀN LỢI TỬ VONG" sat uncited at [1]/[2] every time — and, when the user
pushed back, flipped to "Có được claim" on exactly the same evidence.
"""

from __future__ import annotations

import pytest

from app.generation import generator
from app.generation.coverage_gate import (
    check_verdict,
    correction_instruction,
    correction_messages,
    fallback_answer,
    states_approval,
    states_denial,
    strip_leaked_instructions,
)
from app.models.schemas import DocType, Hit, QdrantPayload

_EXCLUSION = "LOẠI TRỪ TRÁCH NHIỆM BẢO HIỂM"
_DEATH_BENEFIT = "QUYỀN LỢI TỬ VONG LÊN ĐẾN 25 TỶ ĐỒNG"
_DISABILITY_BENEFIT = "QUYỀN LỢI THƯƠNG TẬT TOÀN BỘ VĨNH VIỄN"


def _hit(section_path: str, text: str = "") -> Hit:
    payload = QdrantPayload(
        doc_id="d1",
        doc_title="Bảo hiểm liên kết chung",
        section_path=section_path,
        page=None,
        doc_type=DocType.POLICY,
        display_text=text or section_path,
        chunk_index=0,
        ingested_at="2026-01-01T00:00:00+00:00",
    )
    return Hit(
        point_id=f"p-{abs(hash(section_path)) % 10**8}", score=1.0, payload=payload
    )


# The context as the reported conversation actually had it: benefits first
# (payout_clauses_first did its job), exclusions third.
def _reported_context() -> list[Hit]:
    return [
        _hit(_DISABILITY_BENEFIT),
        _hit(_DEATH_BENEFIT),
        _hit(_EXCLUSION, "Người được bảo hiểm tham gia đua xe ô tô, mô tô..."),
    ]


class TestVerdictDetection:
    def test_reads_a_denial(self) -> None:
        assert states_denial("Không được claim.")
        assert states_denial("Vì vậy sự kiện này không được chi trả .")

    def test_reads_an_approval(self) -> None:
        assert states_approval("Có được claim.")
        assert states_approval("Do đó có thể được chi trả .")

    def test_a_denial_never_also_reads_as_an_approval(self) -> None:
        """ "không được chi trả" contains "được chi trả" — the negation must win."""
        assert not states_approval("Không được chi trả.")

    def test_an_enumerated_answer_states_no_verdict(self) -> None:
        answer = (
            "Trường hợp 1 — Nếu tai nạn dẫn đến tử vong: xem [2].\n"
            "Trường hợp 2 — Nếu dẫn đến thương tật toàn bộ vĩnh viễn: xem [1].\n"
            "Cần kiểm tra thêm: hợp đồng có hiệu lực không."
        )
        assert not states_denial(answer)


class TestVerdictRegion:
    """A conclusion is stated at the top or in the summary, never mid-answer."""

    def test_naming_an_exclusion_mid_answer_is_not_a_verdict(self) -> None:
        """A correctly enumerated answer MUST discuss exclusions to be useful.

        Without region scoping, the markers added after the production replay
        ("thuộc trường hợp loại trừ") would fire on every good answer.
        """
        answer = (
            "Trường hợp 1 — Nếu sự kiện dẫn đến TỬ VONG: được chi trả theo [2].\n\n"
            + "Phân tích các điều loại trừ: điều khoản nêu rằng người tham gia "
            "đua xe thì thuộc trường hợp loại trừ, nhưng tình huống trong câu "
            "hỏi là tai nạn giao thông thông thường nên điều đó không áp dụng. "
            * 6
            + "\n\n**Kết luận:** sự kiện được chi trả theo [2]; cần kiểm tra "
            "thêm hiệu lực hợp đồng."
        )
        assert not states_denial(answer)

    def test_a_denial_in_the_closing_summary_is_caught(self) -> None:
        answer = (
            "Phân tích chi tiết từng quyền lợi và từng điều khoản. " * 20
            + "\n\n**Kết luận:** sự kiện này không thuộc quyền lợi tử vong."
        )
        assert states_denial(answer)

    def test_the_production_phrasing_is_now_a_denial(self) -> None:
        """None of these said "không được chi trả", so the gate stayed silent."""
        assert states_denial("Kết luận: không thuộc quyền lợi tử vong")
        assert states_denial("Tóm lại, thuộc trường hợp bị loại trừ")


class TestLeakedInstructions:
    def test_strips_the_echoed_repair_steps(self) -> None:
        """Verbatim from the production replay — visible in all four turns."""
        answer = (
            "**1. Đọc đoạn quyền lợi [4] và xác định sự kiện trong câu hỏi có "
            "thuộc quyền lợi nào không, trích dẫn [n] cho từng quyền lợi.**\n"
            "\n"
            "- **Quyền lợi tử vong:** được chi trả theo [2].\n"
            "\n"
            "**3. Sau đó xét các điều loại trừ, và với mỗi điều nêu rõ ĐIỀU "
            "KIỆN áp dụng.**\n"
            "\n"
            "- Điều 8 không áp dụng."
        )
        out = strip_leaked_instructions(answer)
        assert "Đọc đoạn quyền lợi" not in out
        assert "Sau đó xét các điều loại trừ" not in out
        # The actual answer content survives untouched.
        assert "**Quyền lợi tử vong:** được chi trả theo [2]." in out
        assert "Điều 8 không áp dụng." in out

    def test_leaves_ordinary_numbered_prose_alone(self) -> None:
        answer = "1. Hợp đồng phải đang có hiệu lực.\n2. Cần có giấy ra viện."
        assert strip_leaked_instructions(answer) == answer

    def test_correction_instruction_is_no_longer_a_numbered_template(self) -> None:
        """It was reproduced as headings because it looked like an outline."""
        problem = check_verdict("Không được claim [3].", _reported_context())
        assert problem is not None
        text = correction_instruction(problem)
        assert "\n1." not in text and "\n2." not in text
        assert "KHÔNG nhắc lại" in text


class TestGate:
    def test_flags_the_reported_denial_that_cited_only_the_exclusion(self) -> None:
        answer = (
            "Không được claim.\n\nTheo [3] LOẠI TRỪ TRÁCH NHIỆM BẢO HIỂM, "
            "bị tai nạn xe khi đi du lịch thuộc loại trừ."
        )
        problem = check_verdict(answer, _reported_context())
        assert problem is not None
        assert problem.kind == "denial"
        assert problem.uncited_benefits == (1, 2)

    def test_flags_the_sycophantic_flip_on_the_same_evidence(self) -> None:
        """Turn 3: the user pushed back and the verdict flipped, still uncited.

        Reaching "được chi trả" from the event's ABSENCE in the exclusion list
        is the same absence-reasoning as the denial, landing the other way.
        """
        answer = (
            "Có được claim.\n\nTheo [3], tình huống này không thuộc danh sách "
            "loại trừ, nên có thể được chi trả."
        )
        problem = check_verdict(answer, _reported_context())
        assert problem is not None
        assert problem.kind == "approval"

    def test_passes_an_answer_that_cited_a_benefit_clause(self) -> None:
        answer = (
            "Theo [2] Quyền lợi tử vong, tai nạn xe dẫn đến tử vong được chi "
            "trả; [3] chỉ loại trừ hoạt động đua xe thể thao."
        )
        assert check_verdict(answer, _reported_context()) is None

    def test_passes_an_answer_that_reaches_no_verdict(self) -> None:
        answer = "Tài liệu nêu các trường hợp sau, cần đối chiếu thêm."
        assert check_verdict(answer, _reported_context()) is None

    def test_silent_when_no_benefit_clause_was_retrieved_at_all(self) -> None:
        """That state is ``coverage.no_payout_clause_retrieved``'s job.

        It is handled BEFORE generation by the prompt block forbidding any
        conclusion; the gate must not also fire, since there is no benefit
        clause the answer could have cited.
        """
        exclusion_only = [_hit(_EXCLUSION), _hit("THỜI GIAN CHỜ")]
        assert check_verdict("Không được claim.", exclusion_only) is None

    def test_silent_on_an_empty_context(self) -> None:
        assert check_verdict("Không được claim.", []) is None


class TestCorrection:
    def test_correction_names_the_specific_blocks_that_were_skipped(self) -> None:
        problem = check_verdict("Không được claim, theo [3].", _reported_context())
        assert problem is not None
        text = correction_instruction(problem)
        assert "[1], [2]" in text
        assert "KHÔNG được chi trả" in text
        # It must re-state the banned inference, not just ask for a redo.
        assert "danh sách các trường hợp được bảo hiểm" in text

    def test_correction_messages_replay_the_rejected_answer(self) -> None:
        base = [{"role": "system", "content": "..."}]
        problem = check_verdict("Không được claim [3].", _reported_context())
        assert problem is not None
        out = correction_messages(base, "Không được claim [3].", problem)
        assert out[:1] == base
        assert out[-2] == {"role": "assistant", "content": "Không được claim [3]."}
        assert out[-1]["role"] == "user"


class TestFallback:
    def test_enumerates_the_branches_without_reaching_a_verdict(self) -> None:
        text = fallback_answer(_reported_context())
        assert not states_denial(text)
        assert not states_approval(text)
        # Every benefit clause is offered with its citation number.
        assert "[1]" in text and "[2]" in text
        assert _DEATH_BENEFIT in text
        assert _EXCLUSION in text
        assert "Cần kiểm tra thêm" in text

    def test_survives_the_gate_it_is_the_fallback_for(self) -> None:
        hits = _reported_context()
        assert check_verdict(fallback_answer(hits), hits) is None


@pytest.fixture(autouse=True)
def _no_llm_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the second-pass verifier out of the deterministic tests.

    It makes a real Ollama call; these tests are about the gate's own logic.
    ``tests/test_verify.py`` covers the verifier itself.
    """
    monkeypatch.setattr(generator, "verify_answer", lambda q, a: None)


class TestGatedGeneration:
    """The retry loop around the model, with the Ollama call stubbed out."""

    def test_accepts_a_grounded_answer_without_a_second_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        grounded = "Theo [2] Quyền lợi tử vong, trường hợp này được chi trả."
        calls: list[list[dict[str, str]]] = []

        def fake(messages: list[dict[str, str]]) -> str:
            calls.append(messages)
            return grounded

        monkeypatch.setattr(generator, "_chat_raw", fake)
        out = generator._gated_coverage_answer(
            [], _reported_context(), "tai nạn xe tử vong"
        )
        assert out == grounded
        assert len(calls) == 1

    def test_regenerates_the_reported_denial_and_keeps_the_better_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Turn 1 of the reported conversation, then a corrected retry."""
        answers = iter(
            [
                "Không được claim. Theo [3] LOẠI TRỪ, đây là hoạt động đua xe.",
                "Trường hợp tử vong: [2] Quyền lợi tử vong được chi trả. "
                "Điều loại trừ [3] chỉ áp dụng cho đua xe thể thao.",
            ]
        )
        seen: list[list[dict[str, str]]] = []

        def fake(messages: list[dict[str, str]]) -> str:
            seen.append(messages)
            return next(answers)

        monkeypatch.setattr(generator, "_chat_raw", fake)
        out = generator._gated_coverage_answer(
            [{"role": "system", "content": "..."}],
            _reported_context(),
            "tai nạn xe tử vong",
        )
        assert "[2]" in out
        assert not states_denial(out)
        # The retry carried the rejected answer plus the correction turn.
        assert len(seen) == 2
        assert seen[1][-2]["role"] == "assistant"
        assert "Không được claim" in seen[1][-2]["content"]
        assert seen[1][-1]["role"] == "user"

    def test_a_gate_triggered_retry_is_still_sent_to_the_verifier(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The path that shipped a wrong denial in production.

        The retry cited [2], so the verdict gate passed it — and the first
        wiring returned straight out of the deterministic path, so the
        semantic verifier never saw it. A retry that satisfies the citation
        check but not the verifier must fall back, not ship.
        """
        answers = iter(
            [
                "Không được claim. Theo [3] LOẠI TRỪ.",
                "Theo [2] Quyền lợi tử vong, sự kiện này được chi trả.",
            ]
        )
        monkeypatch.setattr(generator, "_chat_raw", lambda m: next(answers))
        monkeypatch.setattr(
            generator, "verify_answer", lambda q, a: "đã thêm tình tiết"
        )
        out = generator._gated_coverage_answer([], _reported_context(), "tai nạn xe")
        # The verifier rejected the retry, so the enumeration ships instead.
        assert "Cần kiểm tra thêm" in out
        assert _DEATH_BENEFIT in out

    def test_falls_back_when_the_model_repeats_the_ungrounded_denial(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The observed case: the same denial twice, once with a block forbidding it.

        An ungrounded verdict must never be what the employee reads, so the
        deterministic enumeration ships instead.
        """
        monkeypatch.setattr(
            generator,
            "_chat_raw",
            lambda messages: "Không được claim. Theo [3] LOẠI TRỪ.",
        )
        out = generator._gated_coverage_answer(
            [], _reported_context(), "tai nạn xe tử vong"
        )
        assert not states_denial(out)
        assert _DEATH_BENEFIT in out
        assert "Cần kiểm tra thêm" in out
