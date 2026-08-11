"""Admin-only operational endpoints: effective config, log viewers, offline eval runs.

Conversation history is deliberately NOT exposed here — employee chat threads
are private per-account (see app/api/conversations.py).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app import auth
from app.config.settings import settings
from app.vn_time import VN_TZ, parse_ts, since_hours_ago

logger = logging.getLogger("bv-ai-agent.admin")

router = APIRouter(tags=["admin"])


class AdminConfigResponse(BaseModel):
    chat_model: str
    embed_model: str
    retrieve_top_k: int
    rerank_top_k: int
    rerank_min_score: float
    departments: list[str]
    api_public_base_url: str
    query_timing_log_enabled: bool
    feedback_log_enabled: bool
    note: str = (
        "Các giá trị đọc từ .env khi khởi động dịch vụ. "
        "Thay đổi yêu cầu sửa .env và khởi động lại."
    )


class FeedbackRecord(BaseModel):
    ts: str
    completion_id: str
    reason: str


class FeedbackLogResponse(BaseModel):
    records: list[FeedbackRecord]
    path: str


class QueryTimingRecord(BaseModel):
    ts: str
    mode: str | None = None
    elapsed_ms: float | None = None
    first_token_ms: float | None = None
    n_hits: int | None = None


class QueryTimingLogResponse(BaseModel):
    records: list[QueryTimingRecord]
    path: str


class EvalRunSummary(BaseModel):
    file: str
    mtime: str
    n: int | None = None
    doc_hit_rate: float | None = None
    refusal_correct_rate: float | None = None
    assertion_pass_rate: float | None = None
    chat_model: str | None = None


class EvalRunsResponse(BaseModel):
    runs: list[EvalRunSummary]
    results_dir: str


def _read_jsonl(path: Path, since: datetime | None, limit: int) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if since is not None:
                    ts_raw = rec.get("ts")
                    if ts_raw:
                        ts = parse_ts(str(ts_raw))
                        if ts is not None and ts < since:
                            continue
                out.append(rec)
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return []
    return out[-limit:]


@router.get(
    "/admin/config",
    dependencies=[Depends(auth.require_admin)],
    response_model=AdminConfigResponse,
)
async def admin_config() -> AdminConfigResponse:
    return AdminConfigResponse(
        chat_model=settings.chat_model,
        embed_model=settings.embed_model,
        retrieve_top_k=settings.retrieve_top_k,
        rerank_top_k=settings.rerank_top_k,
        rerank_min_score=settings.rerank_min_score,
        departments=list(settings.departments),
        api_public_base_url=settings.api_public_base_url,
        query_timing_log_enabled=settings.query_timing_log_enabled,
        feedback_log_enabled=settings.feedback_log_enabled,
    )


@router.get(
    "/admin/logs/feedback",
    dependencies=[Depends(auth.require_admin)],
    response_model=FeedbackLogResponse,
)
async def admin_feedback_log(
    hours: float | None = Query(default=168, ge=0),
    limit: int = Query(default=200, ge=1, le=2000),
) -> FeedbackLogResponse:
    path = Path(settings.feedback_log_path)
    since = since_hours_ago(hours) if hours and hours > 0 else None
    raw = _read_jsonl(path, since, limit)
    records = [
        FeedbackRecord(
            ts=str(r.get("ts", "")),
            completion_id=str(r.get("completion_id", "")),
            reason=str(r.get("reason", "")),
        )
        for r in raw
        if r.get("completion_id")
    ]
    return FeedbackLogResponse(records=records, path=str(path))


@router.get(
    "/admin/logs/queries",
    dependencies=[Depends(auth.require_admin)],
    response_model=QueryTimingLogResponse,
)
async def admin_query_timing_log(
    hours: float | None = Query(default=24, ge=0),
    limit: int = Query(default=200, ge=1, le=2000),
) -> QueryTimingLogResponse:
    path = Path(settings.query_timing_log_path)
    since = since_hours_ago(hours) if hours and hours > 0 else None
    raw = _read_jsonl(path, since, limit)
    records = [
        QueryTimingRecord(
            ts=str(r.get("ts", "")),
            mode=r.get("mode"),
            elapsed_ms=r.get("elapsed_ms"),
            first_token_ms=r.get("first_token_ms"),
            n_hits=r.get("n_hits"),
        )
        for r in raw
        if r.get("ts")
    ]
    return QueryTimingLogResponse(records=records, path=str(path))


@router.get(
    "/admin/eval-runs",
    dependencies=[Depends(auth.require_admin)],
    response_model=EvalRunsResponse,
)
async def admin_eval_runs(
    limit: int = Query(default=20, ge=1, le=500),
) -> EvalRunsResponse:
    results_dir = Path(__file__).resolve().parents[2] / "eval" / "results"
    if not results_dir.is_dir():
        return EvalRunsResponse(runs=[], results_dir=str(results_dir))
    files = sorted(
        results_dir.glob("run-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    runs: list[EvalRunSummary] = []
    for path in files[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        overall = data.get("overall") or {}
        settings_block = data.get("settings") or {}
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=VN_TZ).isoformat()
        runs.append(
            EvalRunSummary(
                file=path.name,
                mtime=mtime,
                n=overall.get("n"),
                doc_hit_rate=overall.get("doc_hit_rate"),
                refusal_correct_rate=overall.get("refusal_correct_rate"),
                assertion_pass_rate=overall.get("assertion_pass_rate"),
                chat_model=settings_block.get("chat_model"),
            )
        )
    return EvalRunsResponse(runs=runs, results_dir=str(results_dir))


@router.get("/admin/eval-runs/{filename}", dependencies=[Depends(auth.require_admin)])
async def admin_eval_run_detail(filename: str) -> dict:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Tên tệp không hợp lệ.")
    results_dir = Path(__file__).resolve().parents[2] / "eval" / "results"
    path = results_dir / filename
    if (
        not path.is_file()
        or not path.name.startswith("run-")
        or not path.name.endswith(".json")
    ):
        raise HTTPException(status_code=404, detail="Không tìm thấy báo cáo.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Không đọc được báo cáo.") from exc
