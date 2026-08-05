"""Dangling-citation check: an ``[n]`` marker the model wrote that resolves to
no line in the appended "Nguồn tham khảo" block (ADM2, 2026-08-05 audit).

Until this module existed, this was only an OFFLINE metric
(``eval/run_ragas.py::citation_check``) — a live answer could ship a dangling
``[n]`` with nothing catching it. Shared here so ``eval/run_ragas.py`` and
``app/generation/generator.py`` use the exact same definition instead of two
copies that could drift apart.

Only ever operates on the model's own prose BEFORE ``format_sources`` is
appended — running this on the full answer+sources text would treat the
sources block's own ``- [1] ...`` lines as citations to check, which is
trivially always non-dangling and defeats the point.
"""

from __future__ import annotations

import re

from app.generation.prompts import citation_numbers
from app.models.schemas import Hit

_CITATION_MARKER_RE = re.compile(r"\[(\d{1,2})\]")

# Streaming answers can't un-send an already-displayed token (see
# generator._stream_chat), so a dangling citation there is flagged instead of
# stripped — this note is appended as part of the suffix, right before the
# sources block, so an employee reading a stray [7] knows to disregard it.
DANGLING_CITATION_NOTICE = (
    "_Lưu ý: câu trả lời có trích dẫn một nguồn không có trong danh sách bên "
    "dưới; vui lòng bỏ qua trích dẫn đó._"
)


def resolvable_citation_numbers(hits: list[Hit]) -> set[int]:
    """The ``[n]`` numbers that will actually appear in ``format_sources(hits)``."""
    return set(citation_numbers(hits))


def cited_numbers(text: str) -> set[int]:
    """Every ``[n]`` marker number written in ``text``."""
    return {int(n) for n in _CITATION_MARKER_RE.findall(text)}


def has_dangling_citation(text: str, hits: list[Hit]) -> bool:
    """True when ``text`` cites an ``[n]`` that ``hits`` cannot resolve."""
    return bool(cited_numbers(text) - resolvable_citation_numbers(hits))


def strip_dangling_citations(text: str, hits: list[Hit]) -> str:
    """Remove every ``[n]`` marker in ``text`` that doesn't resolve to a source.

    Non-streaming (or already-buffered, e.g. the coverage-gate path) answers
    only — the full text must already be known and not yet shown to the user.
    """
    valid = resolvable_citation_numbers(hits)

    def _sub(match: re.Match[str]) -> str:
        return match.group(0) if int(match.group(1)) in valid else ""

    return _CITATION_MARKER_RE.sub(_sub, text)
