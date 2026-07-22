"""Evaluation harness for the golden set (eval/golden_set.jsonl).

Scores the production query flow (glossary expansion -> hybrid search ->
rerank -> generation; mirrors ``app.api.chat._retrieve`` — keep them in sync)
with RAGAS-style metrics, fully offline:

* **Context precision/recall** — deterministic, from the golden set's labeled
  ``source_doc``/``source_section``: was the right document (and section)
  retrieved, and at what rank (MRR)? Reported both before and after reranking
  so a miss can be attributed to search vs. the reranker.
* **Faithfulness / answer correctness** — judged by the local Ollama model
  (binary verdicts; a small local judge is unreliable on graded scales).
* **Rule compliance** — refusal accuracy, false-refusal rate, citation
  presence, and the mandatory calculation disclaimer (CLAUDE.md answering rules).
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

from app.api.ingest import doc_id_for_filename  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.generation import generator  # noqa: E402
from app.generation.prompts import REFUSAL_MESSAGE  # noqa: E402
from app.models.schemas import Hit  # noqa: E402
from app.retrieval.metric_guard import filter_metric_mismatch  # noqa: E402
from app.retrieval.query_expansion import expand_query  # noqa: E402
from app.retrieval.reranker import rerank  # noqa: E402
from app.retrieval.retriever import hybrid_search  # noqa: E402

_GOLDEN_PATH = Path(__file__).resolve().parent / "golden_set.jsonl"
_RESULTS_DIR = Path(__file__).resolve().parent / "results"

_SOURCES_HEADER = "**Nguồn tham khảo:**"
_CITATION_RE = re.compile(r"\[[^\[\]]{2,}\]")
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


def check_answer(item: GoldenItem, answer: str) -> dict[str, bool | None]:
    """Deterministic rule-compliance checks on one answer (None = not applicable)."""
    body = strip_sources(answer)
    refused = is_refusal(body)
    checks: dict[str, bool | None] = {
        "refusal_correct": None,
        "false_refusal": None,
        "has_citation": None,
        "has_disclaimer": None,
    }
    if item.category == "refusal":
        checks["refusal_correct"] = refused
        return checks
    checks["false_refusal"] = refused
    if not refused:
        checks["has_citation"] = bool(_CITATION_RE.search(body))
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
    """Run one golden question through retrieval (+ generation + judge)."""
    row = Row(id=item.id, category=item.category)
    expected_doc_id = (
        doc_id_for_filename(source_filename(item.source_doc))
        if item.source_doc
        else None
    )

    t0 = time.perf_counter()
    # No chat history in the golden set, so the standalone rewrite is a no-op
    # and deliberately skipped (mirrors app.api.chat._retrieve gating).
    fused = hybrid_search(expand_query(item.question))
    hits: list[Hit] = rerank(item.question, fused)
    if settings.metric_guard_enabled:
        hits = filter_metric_mismatch(item.question, hits)
    row.retrieval_ms = (time.perf_counter() - t0) * 1000
    row.n_hits = len(hits)

    if expected_doc_id is not None:
        row.fused_doc_rank = doc_rank(
            [h.payload.doc_id for h in fused], expected_doc_id
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
    # Mirror the chat endpoint: zero surviving hits either fall back to a
    # labeled general-knowledge answer or refuse deterministically, matching
    # settings.hybrid_fallback_enabled (app/api/chat.py).
    if hits:
        answer = generator.generate_answer(item.question, hits)
    elif settings.hybrid_fallback_enabled:
        answer = generator.generate_hybrid_answer(item.question)
    else:
        answer = REFUSAL_MESSAGE
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
            contexts = "\n\n".join(h.payload.display_text for h in hits)
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
        "disclaimer_rate": _rate(_collect(rows, "has_disclaimer")),
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
        print(f"[{i}/{len(items)}] {item.id} ({item.category}): {item.question[:70]}")
        row = evaluate_item(
            item, generate=not args.retrieval_only, judge=not args.no_judge
        )
        rows.append(row)

    _print_summary("overall", summarize(rows))
    for category in sorted({r.category for r in rows}):
        _print_summary(category, summarize([r for r in rows if r.category == category]))

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
        "rows": [asdict(r) for r in rows],
    }
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
