"""Evaluation harness for the golden set (eval/golden_set.jsonl).

Scores the production query flow with RAGAS-style metrics, fully offline. It
drives the SAME decision tree the chat endpoint uses (``app.api.chat.plan_response``
— spellcheck gate, product-scope guard, hybrid/refusal fallback, advisory
routing), so a false refusal or a wrong-product refusal shows up here instead of
slipping past a drifting copy of the flow:

* **Context precision/recall** — deterministic, from the golden set's labeled
  ``source_doc``/``source_section``: was the right document (and section)
  retrieved, and at what rank (MRR)? Reported both before and after reranking
  so a miss can be attributed to search vs. the reranker.
* **Content assertions** — per-item ``must_say``/``must_not_say`` checked
  deterministically on the answer text. These, not the judge, are the quality
  gate: exclusion polarity above all.
* **Faithfulness / answer correctness** — judged by the local Ollama model
  (binary verdicts; a small local judge is unreliable on graded scales).
  TREAT AS ADVISORY ONLY: it has returned 1.0 for every category in every run
  so far, including one where the model told an employee that a covered death
  was "không chi trả". It is not in the gate; ``must_say``/``must_not_say`` is.
* **Rule compliance** — refusal accuracy, false-refusal rate, citation
  presence (a ``[n]`` marker that RESOLVES to the sources block) and dangling
  citations, plus the mandatory calculation disclaimer (CLAUDE.md answering rules).
* **Latency** — retrieval and generation wall time per question.

The ``ragas`` package itself is deliberately not used: it drags in the
langchain/datasets stack and is built around API-hosted judges; these metrics
mirror its intent with zero new dependencies and no network use.

Run inside the api container (needs Qdrant, Ollama, and local model weights):

    docker compose exec api python eval/run_ragas.py
    docker compose exec api python eval/run_ragas.py --retrieval-only   # fast pass
    docker compose exec api python eval/run_ragas.py --category formula --no-judge

Results are printed per category and written as JSON under eval/results/
(gitignored) so runs can be compared over time. Faithfulness or context
precision dropping vs. the previous run is a regression — investigate before
merging (skill, section 7).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

# Make `app` importable whether run from the repo root or eval/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.chat import plan_response  # noqa: E402
from app.api.ingest import doc_id_for_filename  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.generation import generator  # noqa: E402
from app.generation.prompts import REFUSAL_MESSAGE  # noqa: E402
from app.models.schemas import ChatMessage  # noqa: E402

_GOLDEN_PATH = Path(__file__).resolve().parent / "golden_set.jsonl"
_RESULTS_DIR = Path(__file__).resolve().parent / "results"

_SOURCES_HEADER = "**Nguồn tham khảo:**"
# Citations are ``[n]`` markers keyed to the numbered context blocks (prompts
# rule 2). A marker only counts when that number is actually listed under
# "Nguồn tham khảo" — an unresolvable [7] is a dangling link for the employee,
# not a citation. The earlier ``\[[^\[\]]{2,}\]`` pattern required two or more
# characters between the brackets and so scored every single-digit marker the
# model writes as "no citation": it read 0.50 on a run whose real rate was 0.925.
_CITATION_MARKER_RE = re.compile(r"\[(\d{1,2})\]")
_SOURCE_LINE_RE = re.compile(r"^- \[(\d{1,2})\]", re.MULTILINE)
_DISCLAIMER = "kiểm tra lại bằng công cụ tính phí chính thức"

_JUDGE_CORRECTNESS_PROMPT = (
    "Bạn là giám khảo chấm điểm hệ thống hỏi đáp tài liệu bảo hiểm.\n"
    "Câu hỏi: {question}\n\n"
    "Đáp án chuẩn: {ground_truth}\n\n"
    "Câu trả lời của hệ thống: {answer}\n\n"
    'Trả về JSON đúng định dạng {{"correct": true}} hoặc {{"correct": false}}.\n'
    '"correct" là true khi câu trả lời của hệ thống nêu được (các) ý chính của '
    "đáp án chuẩn và không mâu thuẫn với đáp án chuẩn; khác biệt về cách diễn "
    "đạt, ký hiệu LaTeX tương đương, hay chi tiết bổ sung đúng thì vẫn là true."
)

_JUDGE_FAITHFULNESS_PROMPT = (
    "Bạn là giám khảo kiểm tra tính trung thực với ngữ cảnh của hệ thống hỏi "
    "đáp tài liệu.\n"
    "Ngữ cảnh:\n{contexts}\n\n"
    "Câu trả lời: {answer}\n\n"
    'Trả về JSON đúng định dạng {{"faithful": true}} hoặc {{"faithful": false}}.\n'
    '"faithful" là true khi mọi khẳng định trong câu trả lời đều được ngữ cảnh '
    "ở trên hỗ trợ trực tiếp (không thêm thông tin ngoài ngữ cảnh)."
)


# --------------------------------------------------------------------------- #
# Golden set + pure scoring helpers (unit-tested in tests/test_eval.py)
# --------------------------------------------------------------------------- #


@dataclass
class GoldenItem:
    """One golden Q/A pair; ``source_doc``/``source_section`` may be None (refusal)."""

    id: str
    category: str
    question: str
    ground_truth: str
    source_doc: str | None = None
    source_section: str | None = None
    notes: str | None = None
    # Deterministic content assertions, checked against the answer prose (see
    # ``assertion_check``). Use them for the properties a wrong answer would be
    # unsafe on — exclusion polarity above all — not for phrasing.
    must_say: list[str] = field(default_factory=list)
    must_not_say: list[str] = field(default_factory=list)
    # Prior turns replayed before ``question``, as ``{"role", "content"}`` dicts.
    # Without this the set could only express opening questions, and the whole
    # 2026-07-27 coverage failure lived in the FOLLOW-UPS: a bare "tai nạn xe tử
    # vong cơ mà" carries no coverage marker of its own, so the guards that
    # depend on conversation state (``coverage.is_coverage_thread``,
    # ``conversation_scope``) were untested by construction.
    history: list[dict[str, str]] = field(default_factory=list)


def load_golden(path: Path = _GOLDEN_PATH) -> list[GoldenItem]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(GoldenItem(**json.loads(line)))
    return items


def source_filename(source_doc: str | None) -> str | None:
    """The bare filename of a golden ``source_doc`` (drops a "glossary:" prefix)."""
    if not source_doc:
        return None
    return source_doc.split(":", 1)[-1]


def section_matches(expected: str | None, section_path: str) -> bool:
    """Loose section match: one path contains the other (chunks may be deeper)."""
    if not expected:
        return False
    expected, actual = expected.strip(), section_path.strip()
    return bool(expected) and (expected in actual or actual in expected)


def doc_rank(doc_ids: list[str], expected_doc_id: str | None) -> int | None:
    """1-based rank of the first hit from the expected document, else None."""
    if expected_doc_id is None:
        return None
    for rank, doc_id in enumerate(doc_ids, start=1):
        if doc_id == expected_doc_id:
            return rank
    return None


def strip_sources(answer: str) -> str:
    """Answer text without the appended sources block (which always contains
    ``[n]`` markers and would make the citation check trivially pass)."""
    return answer.split(_SOURCES_HEADER, 1)[0].strip()


def is_refusal(answer: str) -> bool:
    return REFUSAL_MESSAGE.rstrip(".") in answer


def sources_numbers(answer: str) -> set[int]:
    """The ``[n]`` numbers listed in the appended "Nguồn tham khảo" block."""
    _, _, block = answer.partition(_SOURCES_HEADER)
    return {int(n) for n in _SOURCE_LINE_RE.findall(block)}


def citation_check(answer: str) -> tuple[bool, bool]:
    """``(has_citation, has_dangling_citation)`` for one answer.

    ``has_citation``: at least one ``[n]`` in the model's own prose that the
    sources block actually lists — i.e. a marker the employee can click.
    ``has_dangling_citation``: some ``[n]`` points at a source that is not
    there. That is worse than no citation (it invents provenance), so it is
    counted separately rather than folded into the rate.
    """
    listed = sources_numbers(answer)
    cited = {int(n) for n in _CITATION_MARKER_RE.findall(strip_sources(answer))}
    return bool(cited & listed), bool(cited - listed)


def assertion_check(item: GoldenItem, answer: str) -> bool | None:
    """Deterministic content assertions from the golden item; None when it has none.

    This is the gate the LLM judge could not be: the judge returned 1.0 for
    every category in every stored run, including the run where the model
    inverted exclusion polarity and told an employee a covered death was
    "không chi trả". ``must_say`` / ``must_not_say`` are matched
    case-insensitively against the model's prose with the sources block
    stripped (source titles must not satisfy an assertion).
    """
    if not item.must_say and not item.must_not_say:
        return None
    body = strip_sources(answer).casefold()
    return all(s.casefold() in body for s in item.must_say) and not any(
        s.casefold() in body for s in item.must_not_say
    )


def check_answer(item: GoldenItem, answer: str) -> dict[str, bool | None]:
    """Deterministic rule-compliance checks on one answer (None = not applicable)."""
    body = strip_sources(answer)
    refused = is_refusal(body)
    checks: dict[str, bool | None] = {
        "refusal_correct": None,
        "false_refusal": None,
        "has_citation": None,
        "has_dangling_citation": None,
        "has_disclaimer": None,
        "assertions_pass": None,
    }
    if item.category == "refusal":
        checks["refusal_correct"] = refused
        return checks
    checks["false_refusal"] = refused
    checks["assertions_pass"] = assertion_check(item, answer)
    if not refused:
        checks["has_citation"], checks["has_dangling_citation"] = citation_check(answer)
    if item.category == "calculation" and not refused:
        checks["has_disclaimer"] = _DISCLAIMER in body
    return checks


# --------------------------------------------------------------------------- #
# Pipeline execution + LLM judge
# --------------------------------------------------------------------------- #


@dataclass
class Row:
    """Everything measured for one golden question."""

    id: str
    category: str
    retrieval_ms: float = 0.0
    generation_ms: float | None = None
    fused_doc_rank: int | None = None
    reranked_doc_rank: int | None = None
    doc_hit: bool | None = None
    section_hit: bool | None = None
    n_hits: int = 0
    # Which branch of the production decision tree fired (grounded / advisory /
    # hybrid / refusal / clarification) — records guard behaviour the old
    # inline flow never exercised.
    plan_kind: str | None = None
    answer: str | None = None
    checks: dict[str, bool | None] = field(default_factory=dict)
    judge_correct: bool | None = None
    judge_faithful: bool | None = None


def _judge(prompt: str, key: str) -> bool | None:
    """Ask the local model for a binary JSON verdict; None when unavailable."""
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.chat_model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "format": "json",
                "keep_alive": settings.ollama_keep_alive,
                "options": {"temperature": 0.0},
            },
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        verdict = json.loads(resp.json().get("response", "{}"))
        value = verdict.get(key)
        return bool(value) if isinstance(value, bool) else None
    except (httpx.HTTPError, ValueError):
        return None


def evaluate_item(
    item: GoldenItem, *, generate: bool = True, judge: bool = True
) -> Row:
    """Run one golden question through the REAL pipeline (+ generation + judge).

    ``plan_response`` runs the exact production decision tree: glossary
    expansion, hybrid search, rerank, metric guard, the product-scope guard,
    and the hybrid/refusal/advisory routing. ``plan.kind`` records which branch
    fired. Items carrying ``history`` replay those turns first, so a golden
    case can assert on a FOLLOW-UP — the shape the coverage failure took.
    """
    row = Row(id=item.id, category=item.category)
    expected_doc_id = (
        doc_id_for_filename(source_filename(item.source_doc))
        if item.source_doc
        else None
    )

    t0 = time.perf_counter()
    plan = plan_response(item.question, [ChatMessage(**turn) for turn in item.history])
    row.retrieval_ms = (time.perf_counter() - t0) * 1000
    row.plan_kind = plan.kind
    hits = plan.hits
    row.n_hits = len(hits)

    if expected_doc_id is not None:
        row.fused_doc_rank = doc_rank(
            [h.payload.doc_id for h in plan.fused], expected_doc_id
        )
        row.reranked_doc_rank = doc_rank(
            [h.payload.doc_id for h in hits], expected_doc_id
        )
        row.doc_hit = row.reranked_doc_rank is not None
        row.section_hit = any(
            h.payload.doc_id == expected_doc_id
            and section_matches(item.source_section, h.payload.section_path)
            for h in hits
        )

    if not generate:
        return row

    t1 = time.perf_counter()
    # Render the plan the same way the endpoint does. A clarification (spellcheck
    # gate fired on a well-formed golden question) or a refusal both count as
    # "did not answer" for the rule checks below.
    if plan.kind == "grounded":
        answer = generator.generate_answer(
            plan.standalone_query, hits, advisory=plan.advisory
        )
    elif plan.kind == "hybrid":
        answer = generator.generate_hybrid_answer(plan.standalone_query)
    else:  # refusal / clarification
        answer = plan.text or REFUSAL_MESSAGE
    row.generation_ms = (time.perf_counter() - t1) * 1000
    row.answer = answer
    row.checks = check_answer(item, answer)

    if judge and item.category != "refusal" and not is_refusal(answer):
        body = strip_sources(answer)
        row.judge_correct = _judge(
            _JUDGE_CORRECTNESS_PROMPT.format(
                question=item.question,
                ground_truth=item.ground_truth,
                answer=body,
            ),
            "correct",
        )
        if hits:
            # Judge against the text generation actually received (the parent
            # window under parent-child chunking), or faithfulness would be
            # scored against a narrower context than the model saw.
            contexts = "\n\n".join(h.payload.context_text for h in hits)
            row.judge_faithful = _judge(
                _JUDGE_FAITHFULNESS_PROMPT.format(contexts=contexts, answer=body),
                "faithful",
            )
    return row


# --------------------------------------------------------------------------- #
# Aggregation + reporting
# --------------------------------------------------------------------------- #


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _collect(rows: list[Row], attr: str) -> list[bool]:
    out = []
    for row in rows:
        value = getattr(row, attr, None)
        if value is None and attr in row.checks:
            value = row.checks.get(attr)
        if isinstance(value, bool):
            out.append(value)
    return out


def summarize(rows: list[Row]) -> dict[str, Any]:
    """Aggregate metric rates over a set of rows (None = no applicable rows)."""
    ranks = [r.reranked_doc_rank for r in rows if r.reranked_doc_rank is not None]
    with_doc = [r for r in rows if r.doc_hit is not None]
    retrieval_times = [r.retrieval_ms for r in rows]
    generation_times = [r.generation_ms for r in rows if r.generation_ms is not None]
    return {
        "n": len(rows),
        "doc_hit_rate": _rate([bool(r.doc_hit) for r in with_doc]),
        "section_hit_rate": _rate([bool(r.section_hit) for r in with_doc]),
        "fused_doc_hit_rate": _rate([r.fused_doc_rank is not None for r in with_doc]),
        "mrr": round(sum(1.0 / r for r in ranks) / len(with_doc), 3)
        if with_doc
        else None,
        "refusal_correct_rate": _rate(_collect(rows, "refusal_correct")),
        "false_refusal_rate": _rate(_collect(rows, "false_refusal")),
        "citation_rate": _rate(_collect(rows, "has_citation")),
        "dangling_citation_rate": _rate(_collect(rows, "has_dangling_citation")),
        "disclaimer_rate": _rate(_collect(rows, "has_disclaimer")),
        "assertion_pass_rate": _rate(_collect(rows, "assertions_pass")),
        "judge_correct_rate": _rate(_collect(rows, "judge_correct")),
        "judge_faithful_rate": _rate(_collect(rows, "judge_faithful")),
        "retrieval_ms_mean": round(statistics.mean(retrieval_times), 1)
        if retrieval_times
        else None,
        "generation_ms_mean": round(statistics.mean(generation_times), 1)
        if generation_times
        else None,
    }


def _print_summary(title: str, summary: dict[str, Any]) -> None:
    print(f"\n== {title} (n={summary['n']}) ==")
    for key, value in summary.items():
        if key != "n" and value is not None:
            print(f"  {key:<24} {value}")


def did_not_answer(row: Row) -> bool:
    """True when an answerable question was NOT answered (refused or clarified).

    Catches both the guard-level refusals/clarifications (visible from
    ``plan_kind`` even in retrieval-only mode) and a model/hybrid refusal in the
    generated text — the two ways a false refusal can happen.
    """
    if row.plan_kind in ("refusal", "clarification"):
        return True
    return bool(row.answer and is_refusal(row.answer))


def leaked_answer(row: Row) -> bool:
    """True when a refusal-category question produced a real answer instead.

    A refusal question refuses either at a guard (``plan_kind == 'refusal'``) or,
    when retrieval finds nothing, at generation via the hybrid prompt. So a
    definite leak is: retrieval surfaced a document (``plan_kind == 'grounded'``),
    or a generated answer exists and is not the refusal. A ``hybrid`` plan with no
    generated answer yet (``--retrieval-only``) is UNDECIDED — not a leak.
    """
    if row.answer is not None:
        return not is_refusal(row.answer) and row.plan_kind not in (
            "refusal",
            "clarification",
        )
    return row.plan_kind == "grounded"


def gate(rows: list[Row]) -> dict[str, list[str]]:
    """Hard pass/fail signals for CI (see ``--strict``).

    ``false_refusals``: answerable questions the pipeline did not answer.
    ``leaked_refusals``: refusal-category questions that got an answer instead.
    ``failed_assertions``: answers that broke a golden item's ``must_say`` /
    ``must_not_say`` — chiefly exclusion polarity, the failure mode that is
    actively unsafe to ship and that the LLM judge scored as correct.
    ``dangling_citations``: answers citing an ``[n]`` with no such source.
    """
    answerable = [r for r in rows if r.category != "refusal"]
    refusal_rows = [r for r in rows if r.category == "refusal"]
    return {
        "false_refusals": [r.id for r in answerable if did_not_answer(r)],
        "leaked_refusals": [r.id for r in refusal_rows if leaked_answer(r)],
        "failed_assertions": [
            r.id for r in rows if r.checks.get("assertions_pass") is False
        ],
        "dangling_citations": [
            r.id for r in rows if r.checks.get("has_dangling_citation") is True
        ],
    }


def _print_gate(rows: list[Row]) -> bool:
    """Print the pass/fail gate; return True when it FAILED."""
    result = gate(rows)
    n_answerable = sum(1 for r in rows if r.category != "refusal")
    n_refusal = sum(1 for r in rows if r.category == "refusal")
    print("\n== GATE ==")
    print(
        f"  false refusals (answerable not answered): "
        f"{len(result['false_refusals'])}/{n_answerable}"
    )
    for rid in result["false_refusals"]:
        print(f"    - {rid}")
    print(
        f"  leaked refusals (should refuse, answered): {len(result['leaked_refusals'])}/{n_refusal}"
    )
    for rid in result["leaked_refusals"]:
        print(f"    - {rid}")
    n_asserted = sum(1 for r in rows if r.checks.get("assertions_pass") is not None)
    print(f"  failed assertions: {len(result['failed_assertions'])}/{n_asserted}")
    for rid in result["failed_assertions"]:
        print(f"    - {rid}")
    n_cited = sum(1 for r in rows if r.checks.get("has_dangling_citation") is not None)
    print(f"  dangling citations: {len(result['dangling_citations'])}/{n_cited}")
    for rid in result["dangling_citations"]:
        print(f"    - {rid}")
    return any(result.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--limit", type=int, default=None, help="only the first N items"
    )
    parser.add_argument(
        "--category", action="append", default=None, help="only these categories"
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="skip generation + judge (fast retrieval regression check)",
    )
    parser.add_argument(
        "--no-judge", action="store_true", help="skip the LLM judge (keep generation)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if the gate fails (false refusal, leaked refusal, "
        "failed content assertion, or dangling citation) — for CI",
    )
    parser.add_argument("--out", type=Path, default=None, help="results JSON path")
    args = parser.parse_args()

    items = load_golden()
    if args.category:
        items = [i for i in items if i.category in args.category]
    if args.limit:
        items = items[: args.limit]
    if not items:
        raise SystemExit("No golden items match the given filters.")

    rows: list[Row] = []
    for i, item in enumerate(items, start=1):
        # flush: a full run takes tens of minutes on CPU and Python buffers
        # stdout when it isn't a terminal, hiding all progress until the end.
        print(
            f"[{i}/{len(items)}] {item.id} ({item.category}): {item.question[:70]}",
            flush=True,
        )
        row = evaluate_item(
            item, generate=not args.retrieval_only, judge=not args.no_judge
        )
        rows.append(row)

    _print_summary("overall", summarize(rows))
    for category in sorted({r.category for r in rows}):
        _print_summary(category, summarize([r for r in rows if r.category == category]))
    gate_failed = _print_gate(rows)

    out_path = args.out or _RESULTS_DIR / f"run-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "settings": {
            "chat_model": settings.chat_model,
            "retrieve_top_k": settings.retrieve_top_k,
            "rerank_top_k": settings.rerank_top_k,
            "rerank_min_score": settings.rerank_min_score,
        },
        "overall": summarize(rows),
        "by_category": {
            category: summarize([r for r in rows if r.category == category])
            for category in sorted({r.category for r in rows})
        },
        "gate": gate(rows),
        "rows": [asdict(r) for r in rows],
    }
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nResults written to {out_path}")

    if args.strict and gate_failed:
        raise SystemExit("GATE FAILED: see the == GATE == section above.")


if __name__ == "__main__":
    main()
