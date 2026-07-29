"""Coverage questions: keep the benefit side in context, and never deny from absence.

"Tôi bị X thì có được chi trả không?" is the highest-stakes question an employee
asks, and the one the pipeline handled worst. Observed on a real policy PDF
(2026-07-27): retrieval returned a single exclusion section and nothing else,
and the model denied the claim by applying a substandard-health underwriting
clause to a car accident — while its own general-knowledge block said the case
could not be determined. Prompt rule 6(b) already forbade exactly that, in as
many words, so the prompt is not where this gets fixed.

Two pure helpers, both offline and unit-testable:

* ``expand_coverage_query`` biases the search text toward benefit/scope clauses
  so exclusions are never the whole context.
* ``no_payout_clause_retrieved`` reports the state that must never produce a
  denial: nothing in the context says when the Company pays, i.e. the coverage
  side was not retrieved. Generation is then told to enumerate and qualify
  instead of concluding (see ``prompts._COVERAGE_UNDETERMINED_RULE``).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from app.models.schemas import ChatMessage, Hit

# How far back a coverage question keeps colouring its follow-ups.
_HISTORY_TURNS = 6

# Turns that dispute or narrow the previous answer rather than open a new
# topic. Anchored to word starts so "cơ mà" doesn't match inside a longer word.
_PUSHBACK_RE = re.compile(
    r"(?:^|\s)(nhưng|cơ mà|thế còn|thế nếu|còn nếu|vậy còn|sao lại|thế thì)"
    r"(?:\s|,|$)"
)

# "Am I covered?" — an eligibility question, not a request for a number.
_COVERAGE_MARKERS: tuple[str, ...] = (
    "co duoc claim",
    "co duoc chi tra",
    "co duoc boi thuong",
    "co duoc bao hiem",
    "co duoc thanh toan",
    "co duoc tra",
    "duoc claim khong",
    "co bao gom",
    "co thuoc pham vi",
    "co nam trong pham vi",
    "co duoc huong",
    "am i covered",
    "is it covered",
    "will it pay",
)
# An event the employee is asking about, paired with the markers above.
_EVENT_MARKERS: tuple[str, ...] = (
    "tai nan",
    "tu vong",
    "chet",
    "thuong tat",
    "benh",
    "nam vien",
    "phau thuat",
    "thuong",
    "accident",
    "death",
)

# Added to the search text so the benefit/scope side is retrieved alongside any
# exclusion article. These are the section headings a policy uses for coverage.
_BENEFIT_TERMS: tuple[str, ...] = (
    "quyền lợi bảo hiểm",
    "phạm vi bảo hiểm",
    "trường hợp được chi trả",
    "quyền lợi tử vong",
    "quyền lợi thương tật",
)

# A clause that states when the Company DOES pay. Enumerating exclusion
# vocabulary instead was the first design and it was wrong: on the grown
# corpus a coverage question returned supplementary exclusions, accident
# exclusions, the claims-paperwork article, "benefits not included in the main
# product", and the waiting period — no payout clause anywhere — yet none of
# the last three is literally named "loại trừ", so the guard stayed silent in
# exactly the state it exists for. What matters is not how the denial side is
# worded but whether the payout side is present at all.
#
# "Công ty chi trả" is the phrase a Vietnamese policy uses to grant a benefit.
# It is diacritic-folded, so "Công ty KHÔNG chi trả" (exclusion framing) does
# not match it — the negation sits between the two halves.
_PAYOUT_BODY_MARKERS: tuple[str, ...] = (
    "cong ty chi tra",
    "cong ty se chi tra",
    "cong ty thanh toan",
    "duoc chi tra quyen loi",
    "cong ty tra",
)
# Headings that promise the coverage side even if the body is worded oddly.
_PAYOUT_HEADING_MARKERS: tuple[str, ...] = (
    "quyen loi bao hiem",
    "pham vi bao hiem",
    "quyen loi tu vong",
    "quyen loi thuong tat",
    "quyen loi dao han",
    "truong hop duoc chi tra",
)
# ...unless the heading is one of these: a "benefits NOT in this product" or
# waiting-period article looks like a benefit heading but grants nothing.
_NON_PAYOUT_HEADING_MARKERS: tuple[str, ...] = (
    "khong thuoc san pham chinh",
    "khong thuoc pham vi",
    "loai tru",
    "thoi gian cho",
)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def is_coverage_question(query: str) -> bool:
    """True when the user asks whether an event is covered at all."""
    if not query.strip():
        return False
    folded = _fold(query)
    if not any(m in folded for m in _COVERAGE_MARKERS):
        return False
    return any(m in folded for m in _EVENT_MARKERS)


def _disputes_or_refines(query: str) -> bool:
    """True for a turn that argues with or narrows the previous answer.

    Kept WITH diacritics on purpose: folded, "nhưng" (but) collides with
    "những" (the plural marker), which is ordinary vocabulary and would make
    almost every follow-up match.
    """
    return bool(_PUSHBACK_RE.search(unicodedata.normalize("NFC", query).lower()))


def is_coverage_thread(query: str, history: list[ChatMessage]) -> bool:
    """True when this turn continues a coverage question, marker or not.

    ``is_coverage_question`` needs a coverage marker AND an event, which the
    OPENING turn has and its follow-ups do not — nobody repeats "có được chi
    trả không" on turn three. Measured on the reported conversation: turns 2
    and 3 ("tai nạn xe tử vong cơ mà", "nhưng tôi đi đường bị người khác đâm
    mà") both scored False, so the guard fired on those turns only when the
    LLM rewrite happened to reinsert a marker — nondeterministic, and decided
    by the same small model the guard exists to correct.

    So coverage-ness sticks to the conversation, the way ``active_scope``
    makes a product stick: a later turn that names an event or pushes back
    inherits it from the opening question.
    """
    if is_coverage_question(query):
        return True
    folded = _fold(query)
    if not (any(m in folded for m in _EVENT_MARKERS) or _disputes_or_refines(query)):
        return False
    return any(
        is_coverage_question(turn.content)
        for turn in history[-_HISTORY_TURNS:]
        if turn.role == "user"
    )


def expand_coverage_query(query: str) -> str:
    """Append benefit/scope terms so retrieval cannot return exclusions alone.

    Applied only to coverage questions; every other query is returned
    unchanged. The added terms are generic policy headings, not product names,
    so they bias the pool toward the coverage side without scoping it.
    """
    if not is_coverage_question(query):
        return query
    return f"{query} {' '.join(_BENEFIT_TERMS)}"


def grants_a_benefit(hit: Hit) -> bool:
    """True when the chunk states a case in which the Company pays.

    Checked on ``context_text`` — the parent window under parent-child
    chunking — because that is what generation receives: a child cut from the
    middle of a benefit article may not repeat "Công ty chi trả" itself.
    """
    section = _fold(hit.payload.section_path)
    if any(m in section for m in _NON_PAYOUT_HEADING_MARKERS):
        return False
    if any(m in section for m in _PAYOUT_HEADING_MARKERS):
        return True
    return any(m in _fold(hit.payload.context_text) for m in _PAYOUT_BODY_MARKERS)


def backfill_payout_clause(
    hits: list[Hit],
    *,
    search_fn: Callable[[str, list[str]], list[Hit]],
    max_added: int = 2,
    budget: int | None = None,
) -> list[Hit]:
    """Fetch the payout clause when a coverage question retrieved none.

    Measured, and the reason this function exists: with only exclusion,
    waiting-period and paperwork clauses in context, the model answered "có thể
    không được bảo hiểm" whether or not the prompt forbade it — twice, once with
    a block dedicated to forbidding exactly that. It had nothing to build
    "covered" from. Telling a model not to reach the only conclusion its context
    supports does not work; putting the other side of the policy in front of it
    does.

    Searches the SAME documents the coverage question already matched
    (``search_fn`` is expected to filter by ``doc_id``), so this adds the
    benefit article of the product being asked about rather than another
    product's. Returns ``hits`` unchanged when nothing qualifying is found.

    ``budget`` (the reranker's top-k) caps the result: once the context is
    already full, the benefit clauses evict the WEAKEST non-benefit hits rather
    than being appended on top. Appending grew the context from 5 to 7 on the
    reported conversation and the two extra slots went to a marketing figure
    ("Hơn 131.000 tỷ đồng") and a footnote — noise in front of a small model,
    in the answer that least affords distraction. Eviction never touches a
    benefit clause and never runs while there is room to spare, so a thin
    context keeps its exclusions: those still have to be read and applied.
    """
    doc_ids = list(dict.fromkeys(h.payload.doc_id for h in hits))
    if not doc_ids:
        return hits
    seen = {h.point_id for h in hits}
    added = [
        h
        for h in search_fn(" ".join(_BENEFIT_TERMS), doc_ids)
        if h.point_id not in seen and grants_a_benefit(h)
    ][:max_added]
    if not added:
        return hits
    over = len(hits) + len(added) - budget if budget else 0
    if over <= 0:
        return hits + added
    # Evict from the tail (rerank order puts the weakest last), benefits exempt.
    kept: list[Hit] = []
    for hit in reversed(hits):
        if over > 0 and not grants_a_benefit(hit):
            over -= 1
            continue
        kept.append(hit)
    return list(reversed(kept)) + added


def payout_clauses_first(hits: list[Hit]) -> list[Hit]:
    """Reorder a coverage question's context so benefit clauses lead.

    Observed on a real policy: the exclusions page ranked 1 and the model cited
    ONLY that chunk, ignoring the death-benefit and disability clauses at ranks
    2 and 3 that were sitting in the same context — then denied the claim by
    reading the exclusion list as though it were the list of covered risks.
    Retrieval had done its job; the model anchored on what it read first.

    Relative order within each group is preserved, so rerank quality still
    decides ordering among the benefit clauses and among the rest. Nothing is
    dropped: the exclusions still have to be read and applied.
    """
    benefits = [h for h in hits if grants_a_benefit(h)]
    rest = [h for h in hits if not grants_a_benefit(h)]
    return benefits + rest


def no_payout_clause_retrieved(hits: list[Hit]) -> bool:
    """True when NOTHING in the context says when the Company pays.

    That state is not evidence of exclusion — it means the coverage side was
    never retrieved, whether the rest is worded as exclusions, waiting periods,
    "benefits not included in this product", or claims paperwork. A denial
    built on it is unfalsifiable: the model cannot see the clause that would
    have paid out.
    """
    return bool(hits) and not any(grants_a_benefit(h) for h in hits)
