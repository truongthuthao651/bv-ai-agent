"""Eval-harness tests: golden-set schema and the pure scoring helpers.

No Qdrant, Ollama, or model weights — only the deterministic pieces of
eval/run_ragas.py (loading, matching, rule checks, aggregation).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import run_ragas  # noqa: E402
from run_ragas import (  # noqa: E402
    GoldenItem,
    Row,
    check_answer,
    did_not_answer,
    doc_rank,
    gate,
    load_golden,
    section_matches,
    source_filename,
    strip_sources,
    summarize,
)

from app.generation.prompts import REFUSAL_MESSAGE  # noqa: E402


def _item(category: str = "policy_qa") -> GoldenItem:
    return GoldenItem(
        id="qx",
        category=category,
        question="Câu hỏi?",
        ground_truth="Đáp án.",
        source_doc="doc.md",
        source_section="Điều 1",
    )


# --------------------------------------------------------------------------- #
# Golden set stays loadable and well-formed
# --------------------------------------------------------------------------- #


def test_golden_set_loads_and_has_required_fields() -> None:
    items = load_golden()
    assert len(items) >= 27
    assert len({i.id for i in items}) == len(items)  # unique ids
    for item in items:
        assert item.question and item.ground_truth and item.category
        # Only refusal questions may lack a labeled source.
        if item.category != "refusal":
            assert item.source_doc


# --------------------------------------------------------------------------- #
# Matching helpers
# --------------------------------------------------------------------------- #


def test_source_filename_strips_glossary_prefix() -> None:
    assert source_filename("glossary:thuat_ngu.yaml") == "thuat_ngu.yaml"
    assert source_filename("quy_tac.md") == "quy_tac.md"
    assert source_filename(None) is None


def test_section_matches_either_direction_of_containment() -> None:
    assert section_matches("Chương II > Điều 6", "Chương II > Điều 6 > Khoản 1")
    assert section_matches("Chương II > Điều 6 > Khoản 1", "Chương II > Điều 6")
    assert not section_matches("Điều 6", "Chương I > Điều 2")
    assert not section_matches(None, "Điều 6")
    assert not section_matches("", "Điều 6")


def test_doc_rank_is_one_based_first_match() -> None:
    assert doc_rank(["a", "b", "b"], "b") == 2
    assert doc_rank(["a"], "z") is None
    assert doc_rank([], "z") is None
    assert doc_rank(["a"], None) is None


# --------------------------------------------------------------------------- #
# Answer rule checks
# --------------------------------------------------------------------------- #


def test_strip_sources_removes_only_the_appended_block() -> None:
    answer = "Phí thuần là ... [Tài liệu, Điều 1]\n\n**Nguồn tham khảo:**\n- [1] X"
    assert strip_sources(answer) == "Phí thuần là ... [Tài liệu, Điều 1]"
    assert strip_sources("không có nguồn") == "không có nguồn"


def test_check_answer_citation_not_fooled_by_sources_block() -> None:
    # Without stripping, the sources block's own "[1] ..." would always pass.
    answer = "Câu trả lời không trích dẫn.\n\n**Nguồn tham khảo:**\n- [1] X — Điều 1"
    checks = check_answer(_item(), answer)
    assert checks["has_citation"] is False
    assert checks["false_refusal"] is False


def test_check_answer_refusal_category() -> None:
    checks = check_answer(_item("refusal"), REFUSAL_MESSAGE)
    assert checks["refusal_correct"] is True
    assert checks["has_citation"] is None  # not applicable

    checks = check_answer(_item("refusal"), "Tuổi nghỉ hưu là 60. [Tài liệu, Điều 9]")
    assert checks["refusal_correct"] is False


def test_check_answer_calculation_requires_disclaimer() -> None:
    with_disclaimer = (
        "$v = 1/(1+i) \\approx 0,952$ [Tài liệu, Điều 3]. "
        "Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức."
    )
    checks = check_answer(_item("calculation"), with_disclaimer)
    assert checks["has_disclaimer"] is True

    checks = check_answer(_item("calculation"), "$v \\approx 0,952$ [Tài liệu, Điều 3]")
    assert checks["has_disclaimer"] is False


def test_check_answer_flags_false_refusal() -> None:
    checks = check_answer(_item(), REFUSAL_MESSAGE)
    assert checks["false_refusal"] is True
    assert checks["has_citation"] is None  # refused -> citation check n/a


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def test_summarize_rates_and_mrr_count_misses_as_zero() -> None:
    rows = [
        Row(
            id="q1",
            category="policy_qa",
            retrieval_ms=100.0,
            fused_doc_rank=1,
            reranked_doc_rank=1,
            doc_hit=True,
            section_hit=True,
            checks={"has_citation": True, "false_refusal": False},
        ),
        Row(
            id="q2",
            category="policy_qa",
            retrieval_ms=300.0,
            fused_doc_rank=None,
            reranked_doc_rank=None,
            doc_hit=False,
            section_hit=False,
            checks={"has_citation": False, "false_refusal": False},
        ),
    ]
    summary = summarize(rows)
    assert summary["n"] == 2
    assert summary["doc_hit_rate"] == 0.5
    assert summary["fused_doc_hit_rate"] == 0.5
    assert summary["mrr"] == 0.5  # (1/1 + 0) / 2 — a miss contributes zero
    assert summary["citation_rate"] == 0.5
    assert summary["false_refusal_rate"] == 0.0
    assert summary["retrieval_ms_mean"] == 200.0
    assert summary["judge_correct_rate"] is None  # no judged rows


def test_summarize_refusal_rows() -> None:
    rows = [
        Row(id="q1", category="refusal", checks={"refusal_correct": True}),
        Row(id="q2", category="refusal", checks={"refusal_correct": False}),
    ]
    summary = summarize(rows)
    assert summary["refusal_correct_rate"] == 0.5
    assert summary["doc_hit_rate"] is None


def test_run_ragas_module_has_no_import_side_effects() -> None:
    # Importing the harness must never touch Qdrant/Ollama (models are lazy).
    assert callable(run_ragas.main)


# --------------------------------------------------------------------------- #
# False-refusal gate (H7): the eval must catch guard-level refusals
# --------------------------------------------------------------------------- #


def test_did_not_answer_from_plan_kind() -> None:
    # A guard refusal / spellcheck clarification is visible even in
    # retrieval-only mode (no generated answer text yet).
    assert did_not_answer(Row(id="a", category="false_refusal", plan_kind="refusal"))
    assert did_not_answer(Row(id="b", category="policy_qa", plan_kind="clarification"))
    assert not did_not_answer(Row(id="c", category="policy_qa", plan_kind="grounded"))
    assert not did_not_answer(Row(id="d", category="policy_qa", plan_kind="hybrid"))


def test_did_not_answer_from_answer_text() -> None:
    # A model/hybrid refusal in the generated text also counts.
    grounded_refused = Row(
        id="e", category="policy_qa", plan_kind="grounded", answer=REFUSAL_MESSAGE
    )
    assert did_not_answer(grounded_refused)
    answered = Row(
        id="f", category="policy_qa", plan_kind="grounded", answer="Câu trả lời."
    )
    assert not did_not_answer(answered)


def test_gate_flags_false_and_leaked_refusals() -> None:
    rows = [
        Row(id="ok", category="policy_qa", plan_kind="grounded", answer="A."),
        Row(id="fr01", category="false_refusal", plan_kind="refusal"),
        Row(id="ref_ok", category="refusal", plan_kind="refusal"),
        # A refusal-category question that leaked an answer instead of refusing.
        Row(id="ref_leak", category="refusal", plan_kind="grounded", answer="A."),
    ]
    result = gate(rows)
    assert result["false_refusals"] == ["fr01"]
    assert result["leaked_refusals"] == ["ref_leak"]


def test_gate_does_not_flag_undecided_hybrid_refusal_in_retrieval_only() -> None:
    # In --retrieval-only there is no generated answer yet; a refusal question
    # whose retrieval found nothing (plan_kind="hybrid") refuses at generation
    # via the hybrid prompt, so it must NOT be counted as a leak prematurely.
    rows = [
        Row(id="ref_hybrid", category="refusal", plan_kind="hybrid", answer=None),
        # With generation, a hybrid answer that actually refused is correct too.
        Row(
            id="ref_hybrid_refused",
            category="refusal",
            plan_kind="hybrid",
            answer=REFUSAL_MESSAGE,
        ),
    ]
    assert gate(rows)["leaked_refusals"] == []
