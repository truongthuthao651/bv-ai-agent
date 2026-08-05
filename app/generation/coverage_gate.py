"""Post-generation gate on "có được chi trả không" verdicts.

The retrieval-side fixes in ``app/retrieval/coverage.py`` were not enough.
Measured on a real policy PDF over a four-turn conversation (2026-07-27), with
``backfill_payout_clause`` injecting the benefit article and
``payout_clauses_first`` moving it to the head of the context: the answer
denied the claim in EVERY turn and cited only the exclusions page. "QUYỀN LỢI
TỬ VONG" sat at [1]/[2] of the model's own context, uncited, four times out of
four — including on "tai nạn xe tử vong", which that clause answers directly.

So the check runs on the finished answer, the same way the calculation
disclaimer is enforced in code rather than trusted to the prompt:

* A denial is ungrounded while a benefit clause the answer never cited is
  sitting in its context — the model denied without reading the clause that
  would have paid.
* An approval is ungrounded on the same evidence. On turn 3 the user pushed
  back and the verdict flipped to "Có được claim" — still citing only the
  exclusion, now reasoning that the event's ABSENCE from the exclusion list
  proves payment. That reaches a less-wrong verdict by the same wrong method,
  and CLAUDE.md bans absence-reasoning in both directions.

Everything here is pure: an answer string plus the hits that were in context.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.generation.prompts import citation_numbers
from app.models.schemas import Hit
from app.retrieval.coverage import grants_a_benefit
from app.text_utils import fold_text as _fold

_CITATION_RE = re.compile(r"\[(\d+)\]")

# Verdict phrasing, diacritic-folded. "khong duoc chi tra" is a substring of
# neither approval phrase, so the two sets cannot both match on one sentence.
#
# The last four were added after the first production replay: the enumerated
# answer format the shape rule now produces denies in different words. It wrote
# "không thuộc quyền lợi tử vong" and "thuộc trường hợp bị loại trừ" and never
# once said "không được chi trả", so the gate stayed silent through three turns
# of a wrong denial.
_DENIAL_MARKERS: tuple[str, ...] = (
    "khong duoc claim",
    "khong duoc chi tra",
    "khong duoc bao hiem",
    "khong duoc boi thuong",
    "khong duoc thanh toan",
    "khong thuoc pham vi bao hiem",
    "khong nam trong pham vi bao hiem",
    "khong thuoc quyen loi",
    "khong duoc huong quyen loi",
    "thuoc truong hop loai tru",
    "thuoc truong hop bi loai tru",
    "tu choi chi tra",
)
_APPROVAL_MARKERS: tuple[str, ...] = (
    "duoc claim",
    "duoc chi tra",
    "duoc boi thuong",
    "thuoc pham vi bao hiem",
    "thuoc quyen loi",
)

# A verdict is stated in an answer's closing summary, or — when it has none —
# in its opening line. Never in the middle, where a correctly enumerated answer
# MUST discuss exclusions without concluding from them. Scoping the scan is
# what lets the marker set above include "thuộc trường hợp loại trừ", which is
# analysis mid-answer and a conclusion at the end.
#
# Anchored to the START OF A LINE, i.e. a heading. Two earlier attempts failed:
# "vì vậy" / "do đó" land mid-analysis, and a bare substring search for "kết
# luận" matched the LAST one in the answer — which is always the skeleton's own
# "Cần kiểm tra thêm để kết luận:" trailer, so the region never contained the
# verdict and the gate read every answer as stating none.
_CONCLUSION_HEADING_RE = re.compile(
    r"^[\s*_#>-]*(?:kết luận|tóm lại)\b", re.IGNORECASE | re.MULTILINE
)
_LEDE_LINES = 2


def cited_numbers(answer: str) -> set[int]:
    """Citation markers the answer actually used."""
    return {int(m) for m in _CITATION_RE.findall(answer)}


def benefit_numbers(hits: list[Hit]) -> set[int]:
    """Citation numbers of the context blocks that state when the Company pays."""
    return {
        n
        for n, hit in zip(citation_numbers(hits), hits, strict=True)
        if grants_a_benefit(hit)
    }


def verdict_region(answer: str) -> str:
    """The parts of ``answer`` where a conclusion is actually stated.

    The closing summary when the answer has one, otherwise its opening lines —
    the two shapes the failure took: a bare "Không được claim." lede in the
    reported transcript, and a "**Kết luận:**" section in the enumerated format
    the shape rule now produces. Everything between is the case-by-case
    reasoning, where naming an exclusion is exactly what a good answer does.
    """
    normalized = unicodedata.normalize("NFC", answer)
    matches = list(_CONCLUSION_HEADING_RE.finditer(normalized))
    if matches:
        return normalized[matches[-1].start() :]
    lines = [ln for ln in normalized.splitlines() if ln.strip()]
    return "\n".join(lines[:_LEDE_LINES])


def states_denial(answer: str) -> bool:
    """True when the answer concludes the event is NOT paid."""
    return any(m in _fold(verdict_region(answer)) for m in _DENIAL_MARKERS)


def states_approval(answer: str) -> bool:
    """True when the answer concludes the event IS paid.

    Denial markers are checked first and win: "không được chi trả" contains
    "được chi trả", so an answer that denies must not also read as approving.
    """
    folded = _fold(verdict_region(answer))
    if any(m in folded for m in _DENIAL_MARKERS):
        return False
    return any(m in folded for m in _APPROVAL_MARKERS)


@dataclass(frozen=True)
class VerdictProblem:
    """A verdict the retrieved context does not support."""

    kind: Literal["denial", "approval"]
    # Context blocks stating when the Company pays, which the answer ignored.
    uncited_benefits: tuple[int, ...]


def check_verdict(answer: str, hits: list[Hit]) -> VerdictProblem | None:
    """Report a coverage verdict reached without reading the payout side.

    Returns ``None`` when the answer cited at least one benefit clause (it
    engaged with the coverage side, whatever it concluded), when it stated no
    verdict at all (the enumerated-cases shape the prompt asks for), or when no
    benefit clause was in context — that last state is
    ``coverage.no_payout_clause_retrieved``, handled before generation by the
    prompt block that forbids concluding at all.
    """
    benefits = benefit_numbers(hits)
    if not benefits or benefits & cited_numbers(answer):
        return None
    uncited = tuple(sorted(benefits))
    if states_denial(answer):
        return VerdictProblem(kind="denial", uncited_benefits=uncited)
    if states_approval(answer):
        return VerdictProblem(kind="approval", uncited_benefits=uncited)
    return None


def correction_instruction(problem: VerdictProblem) -> str:
    """The corrective user turn asking for one regeneration.

    Names the specific context blocks the answer skipped, because a generic
    "hãy đọc kỹ hơn" produced the same answer again in testing.

    Written as PROSE. The first version was a numbered list of steps and the
    model reproduced it verbatim as the section headings of the user-facing
    answer ("**1. Đọc đoạn quyền lợi [1], [2]...**") — then, once that answer
    entered the history, copied the format into every later turn. An
    instruction shaped like a template gets used as one.
    """
    refs = ", ".join(f"[{n}]" for n in problem.uncited_benefits)
    verdict = "KHÔNG được chi trả" if problem.kind == "denial" else "ĐƯỢC chi trả"
    return (
        f"Câu trả lời vừa rồi kết luận {verdict} nhưng KHÔNG trích dẫn đoạn "
        f"quyền lợi {refs} đang có sẵn trong ngữ cảnh. Mục loại trừ KHÔNG phải "
        "là danh sách các trường hợp được bảo hiểm, nên không được kết luận "
        "chỉ từ mục đó.\n\n"
        f"Hãy viết lại câu trả lời hoàn chỉnh, bắt đầu từ đoạn quyền lợi {refs}: "
        "nêu rõ sự kiện trong câu hỏi có thuộc quyền lợi nào không; trình bày "
        "theo từng trường hợp kèm trích dẫn [n]; chỉ sau đó mới xét từng điều "
        "loại trừ cùng ĐIỀU KIỆN áp dụng của chính điều đó và việc tình huống "
        "người hỏi có thỏa điều kiện ấy hay không; kết thúc bằng những gì còn "
        "cần kiểm tra.\n\n"
        "CHỈ xuất ra câu trả lời cuối cùng dành cho nhân viên. TUYỆT ĐỐI KHÔNG "
        "nhắc lại, đánh số hay in lại các yêu cầu trong tin nhắn này."
    )


# Echoes of the correction/shape instructions that must never reach the user.
# Matched as a whole line so a numbered heading is dropped without touching
# prose that happens to use the same words.
_LEAKED_STEP_RE = re.compile(
    r"^\s*[*_]*\s*\d[.)]\s*[*_]*\s*(?:"
    r"đọc đoạn quyền lợi"
    r"|trình bày theo từng trường hợp"
    r"|sau đó (?:mới )?xét các điều loại trừ"
    r"|kết thúc bằng những gì"
    r")",
    re.IGNORECASE,
)


def strip_leaked_instructions(answer: str) -> str:
    """Drop lines where the model echoed our repair instructions back.

    Belt to the prose rewrite's braces: observed in production, every turn of
    a four-turn conversation carried "**1. Đọc đoạn quyền lợi [4] và xác
    định...**" as a visible heading, because turn 1's corrected answer went
    into the history and the later turns copied its layout.
    """
    kept = [ln for ln in answer.splitlines() if not _LEAKED_STEP_RE.match(ln)]
    return "\n".join(kept).strip()


def correction_messages(
    messages: list[dict[str, str]], answer: str, problem: VerdictProblem
) -> list[dict[str, str]]:
    """``messages`` continued with the rejected answer and the correction turn.

    Replaying the rejected answer matters: the correction refers to "câu trả
    lời vừa rồi", and the model needs to see which one.
    """
    return [
        *messages,
        {"role": "assistant", "content": answer},
        {"role": "user", "content": correction_instruction(problem)},
    ]


def fallback_answer(hits: list[Hit]) -> str:
    """Deterministic answer used when the regeneration trips the gate again.

    Built only from the section headings already in context and their citation
    numbers, so it invents nothing. It exists so an ungrounded verdict is never
    what the employee sees: an answer that lists the branches and refuses to
    conclude is strictly better than a confident wrong "không được chi trả".
    """
    numbers = citation_numbers(hits)
    benefit_lines = [
        f"- [{n}] {hit.payload.doc_title} — {hit.payload.section_path}"
        for n, hit in zip(numbers, hits, strict=True)
        if grants_a_benefit(hit)
    ]
    other_lines = [
        f"- [{n}] {hit.payload.doc_title} — {hit.payload.section_path}"
        for n, hit in zip(numbers, hits, strict=True)
        if not grants_a_benefit(hit)
    ]
    parts = [
        "Câu hỏi này chưa thể kết luận dứt khoát chỉ từ các đoạn tài liệu lấy "
        "được — kết quả phụ thuộc vào quyền lợi nào được kích hoạt và các điều "
        "kiện chưa được nêu trong câu hỏi.",
        "**Các quyền lợi có trong tài liệu — cần đối chiếu trước tiên:**\n"
        + "\n".join(benefit_lines),
    ]
    if other_lines:
        parts.append(
            "**Các điều khoản khác lấy được (loại trừ, điều kiện, thủ tục):**\n"
            + "\n".join(other_lines)
        )
    parts.append(
        # Wording matters: "sự kiện thuộc quyền lợi nào" tripped the approval
        # marker on this very text — the fallback must state no verdict at all.
        "**Cần kiểm tra thêm để kết luận:** hợp đồng có đang hiệu lực không; "
        "sự kiện rơi vào quyền lợi nào ở trên; khách hàng có tham gia sản phẩm "
        "bổ trợ liên quan không; Giấy chứng nhận bảo hiểm có ghi điểm loại trừ "
        "bổ sung riêng không. Vui lòng đối chiếu Quy tắc và Điều khoản sản "
        "phẩm trước khi trả lời khách hàng."
    )
    return "\n\n".join(parts)
