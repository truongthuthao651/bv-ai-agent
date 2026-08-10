"""Strip server-appended artifacts from assistant turns before replaying them.

Open WebUI returns the FULLY RENDERED answer as the assistant turn: the
"Nguồn tham khảo" block, the deterministic disclaimers and the response-time
footer are all streamed as message *content*, so they all come back to us on
the next turn and were replayed to the model verbatim.

That made the model imitate what it saw. Observed on a real policy PDF
(2026-07-27): by the fourth turn the answer contained THREE "Nguồn tham khảo"
blocks — one the model wrote itself, under its own numbering, plus the two the
suffix appended across the exchange. The model's block said [1] = LOẠI TRỪ
while the canonical one said [3] = LOẠI TRỪ, so no citation number resolved
reliably any more, defeating the whole point of ``citation_numbers``. It
compounds: every turn feeds one more pseudo-block back in.

Only the MODEL-FACING path strips these. ``retrieval/conversation_scope.py``
and ``retrieval/comparison.py`` deliberately parse the sources block back out
of history to recover which products a conversation is about, so the raw turns
must stay intact for them — this is applied in ``build_messages``, not at the
endpoint.
"""

from __future__ import annotations

import re

from app.generation.prompts import (
    ADVISORY_DISCLAIMER,
    CALC_DISCLAIMER,
    GENERAL_KNOWLEDGE_DISCLAIMER,
    HYBRID_DISCLAIMER,
    SOURCES_HEADING,
)

# Everything the generator appends after the model's own text. Matched by
# containment on a stripped line, so the italic wrappers (``_..._``) the
# suffixes use don't have to be reproduced here.
_APPENDED_LABELS: tuple[str, ...] = (
    CALC_DISCLAIMER.rstrip("."),
    ADVISORY_DISCLAIMER.rstrip("."),
    GENERAL_KNOWLEDGE_DISCLAIMER.rstrip("."),
    HYBRID_DISCLAIMER.rstrip("."),
)

# The response-time footer (``query_timing.response_time_footer``).
_TIMING_LINE_RE = re.compile(r"^_?⏱\s*Thời gian trả lời:.*$")


def _is_appended_artifact(line: str) -> bool:
    """True for a line the generator appended rather than the model wrote."""
    stripped = line.strip()
    if not stripped:
        return False
    if _TIMING_LINE_RE.match(stripped):
        return True
    return any(label in stripped for label in _APPENDED_LABELS)


def truncate_at_sources_heading(text: str) -> str:
    """Cut ``text`` at a model-written "Nguồn tham khảo" heading.

    The canonical block is appended by ``_sources_suffix`` under
    ``citation_numbers``' numbering; anything the model writes under the same
    heading competes with it and is dropped.
    """
    idx = text.find(SOURCES_HEADING)
    return text[:idx].rstrip() if idx != -1 else text


def strip_appended_artifacts(content: str) -> str:
    """Return ``content`` with generator-appended suffixes removed.

    Cuts at the FIRST "Nguồn tham khảo" heading — everything from there on is
    either the model imitating our block or our own appended one, and neither
    is context the model needs to answer the next question. Remaining
    disclaimer and timing lines are dropped wherever they sit, since the
    general-knowledge label lands between a model-written block and ours.

    Returns "" when nothing but artifacts was there; the caller drops such a
    turn rather than replaying an empty message.
    """
    content = truncate_at_sources_heading(content)
    kept = [ln for ln in content.splitlines() if not _is_appended_artifact(ln)]
    return "\n".join(kept).strip()
