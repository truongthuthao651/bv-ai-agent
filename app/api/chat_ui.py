"""Support endpoints for the ``/chat`` UI (frontend/src/chat/) that aren't
part of the OpenAI-compatible ``/v1`` surface.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Query

from app.models.schemas import FeedbackRequest
from app.query_timing import log_feedback

router = APIRouter(tags=["chat-ui"])

_SUGGESTIONS_VI = (
    Path(__file__).resolve().parents[2] / "scripts" / "prompt_suggestions.json"
)
_SUGGESTIONS_EN = (
    Path(__file__).resolve().parents[2] / "scripts" / "prompt_suggestions_en.json"
)


@router.get("/prompt-suggestions")
async def prompt_suggestions(lang: str | None = Query(default=None)) -> list[dict]:
    """Prompt suggestions for /chat empty state — Vietnamese or English."""
    path = _SUGGESTIONS_EN if lang == "en" else _SUGGESTIONS_VI
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/feedback")
async def feedback(body: FeedbackRequest) -> dict[str, bool]:
    """Thumbs-down signal on one streamed answer (P2-F2, audit/REPORT.md) —
    the only quality signal this app has in production beyond eval/'s golden
    set today. Log-only: no admin-facing view of this yet (a Wave-3-scale
    follow-up once there's enough volume to be worth a screen for), but a
    bad answer now leaves a trace instead of vanishing with no record.
    """
    log_feedback(body.completion_id, body.reason)
    return {"ok": True}
