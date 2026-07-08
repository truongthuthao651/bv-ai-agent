"""Enrichment: build ``embed_text`` from ``display_text`` + verbalizations.

Embeddings match prose, not LaTeX, so each chunk containing a formula gets a
short Vietnamese description of what the formula computes, appended to
``embed_text`` only (never to ``display_text``). Formula verbalization uses the
local LLM via Ollama. Offline batch work — NEVER moved to query time
(skill, section 2).

Figure description (Qwen2.5-VL) arrives with the figure/hard-parser increment.

The verbalizer is injectable so tests run without Ollama.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable

import httpx

from app.config.settings import settings
from app.models.schemas import Chunk

logger = logging.getLogger(__name__)

Verbalizer = Callable[[str], str]

# Inline ($...$) or display ($$...$$) math.
_MATH_RE = re.compile(r"\$\$.+?\$\$|\$[^$\n]+?\$", re.DOTALL)

_VERBALIZE_PROMPT = (
    "Bạn là trợ lý định phí bảo hiểm. Hãy mô tả ngắn gọn bằng tiếng Việt (1–2 câu) "
    "ý nghĩa và mục đích tính toán của (các) công thức trong đoạn sau. Chỉ trả về "
    "phần mô tả, không lặp lại công thức, không thêm lời dẫn.\n\nĐoạn:\n{content}"
)


def has_math(text: str) -> bool:
    """True if the text contains inline or display LaTeX math."""
    return bool(_MATH_RE.search(text))


def _ollama_verbalize(content: str) -> str:
    """Ask the local LLM for a concise Vietnamese description of the formula(s)."""
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.chat_model,
                "prompt": _VERBALIZE_PROMPT.format(content=content),
                "stream": False,
                "think": False,  # qwen3: skip chain-of-thought for batch enrichment
                "options": {"temperature": 0.0},
            },
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Formula verbalization failed, skipping: %s", exc)
        return ""


def enrich_chunks(
    chunks: Iterable[Chunk],
    *,
    enabled: bool | None = None,
    verbalize: Verbalizer | None = None,
) -> list[Chunk]:
    """Append Vietnamese formula verbalizations to each math chunk's embed_text.

    ``enabled`` defaults to ``settings.enable_enrichment``. Mutates and returns
    the chunks. Non-math chunks are left untouched.
    """
    if enabled is None:
        enabled = settings.enable_enrichment
    verbalize = verbalize or _ollama_verbalize

    result: list[Chunk] = []
    for chunk in chunks:
        if enabled and has_math(chunk.display_text):
            description = verbalize(chunk.display_text)
            if description:
                chunk.embed_text = f"{chunk.embed_text}\n\nDiễn giải: {description}"
        result.append(chunk)
    return result
