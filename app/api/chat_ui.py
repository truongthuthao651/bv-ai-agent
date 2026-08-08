"""Support endpoints for the ``/chat`` UI (frontend/src/chat/) that aren't
part of the OpenAI-compatible ``/v1`` surface.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(tags=["chat-ui"])

_SUGGESTIONS_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "prompt_suggestions.json"
)


@router.get("/prompt-suggestions")
async def prompt_suggestions() -> list[dict]:
    """The real Vietnamese prompt suggestions shown in /chat's empty state
    (scripts/prompt_suggestions.json — formerly Open WebUI's, now ours alone
    since Open WebUI was retired).
    """
    return json.loads(_SUGGESTIONS_PATH.read_text(encoding="utf-8"))
