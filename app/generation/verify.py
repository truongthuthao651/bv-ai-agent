"""Second-pass LLM check on a finished coverage answer.

The deterministic gate in ``coverage_gate.py`` can tell whether an answer
CITED a benefit clause. It cannot tell whether the answer then read that clause
correctly, and production showed exactly that failure: the model quoted
"Quyền lợi tử vong được chi trả không phụ thuộc nguyên nhân tử vong là do bệnh
tật hay do tai nạn" as [1] and concluded "không thuộc quyền lợi tử vong" — the
clause's own opposite. It also invented the customer's facts, asserting the
person had been "đua xe" (racing) when the question said an ordinary car
accident on holiday, so the racing exclusion would apply.

Both are semantic, so a second model pass is the available tool. Two caveats
are recorded here rather than discovered again:

* A SMALL LOCAL MODEL IS A WEAK JUDGE. ``eval/run_ragas.py`` documents its own
  local judge returning 1.0 for every category in every run to date, including
  one where the model told an employee that a covered death was "không chi
  trả". Treat this layer as defence in depth, never as a guarantee, and A/B it
  before believing it helps.
* It therefore FAILS OPEN. A verifier that is down, slow, or returns
  unparseable output must never block an answer; every failure path returns
  ``None`` (nothing wrong found) and the answer ships as-is.

The questions are deliberately narrow and binary. A 1.7B model that cannot
grade "is this answer grounded?" can still often decide "does the answer claim
the customer did something the question never mentioned?".
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

_VERIFY_PROMPT = """\
Bạn là bộ phận kiểm tra chất lượng. Đọc CÂU HỎI và CÂU TRẢ LỜI dưới đây rồi \
trả lời đúng hai câu hỏi kiểm tra.

CÂU HỎI CỦA NHÂN VIÊN:
{question}

CÂU TRẢ LỜI CẦN KIỂM TRA:
{answer}

Hai câu hỏi kiểm tra:
1. "them_tinh_tiet": Câu trả lời có khẳng định khách hàng đã làm một việc gì đó \
mà CÂU HỎI không hề nêu hay không? (ví dụ: câu hỏi chỉ nói "tai nạn xe" nhưng \
câu trả lời khẳng định người đó "đua xe", "uống rượu", "không có bằng lái"). \
Chỉ tính khi câu trả lời KHẲNG ĐỊNH điều đó về khách hàng; việc trích dẫn hay \
liệt kê nội dung điều khoản thì KHÔNG tính.
2. "nguoc_trich_dan": Câu trả lời có kết luận ngược với chính đoạn tài liệu mà \
nó trích dẫn hay không? (ví dụ: trích dẫn "được chi trả không phụ thuộc nguyên \
nhân" rồi lại kết luận "không thuộc quyền lợi").

Chỉ trả về JSON đúng định dạng, không giải thích:
{{"them_tinh_tiet": true/false, "nguoc_trich_dan": true/false}}\
"""

_INVENTED_FACTS_REASON = (
    "Câu trả lời vừa rồi KHẲNG ĐỊNH về khách hàng một tình tiết mà câu hỏi "
    "không hề nêu (ví dụ suy diễn 'tai nạn xe' thành 'đua xe'). Hãy viết lại, "
    "chỉ dùng đúng những dữ kiện có trong câu hỏi; nếu thiếu dữ kiện để biết "
    "một điều loại trừ có áp dụng hay không thì đưa điều đó vào phần cần kiểm "
    "tra thêm, KHÔNG tự giả định là có."
)
_CONTRADICTS_REASON = (
    "Câu trả lời vừa rồi kết luận NGƯỢC với chính đoạn tài liệu mà nó trích "
    "dẫn. Hãy đọc lại đoạn quyền lợi đã trích dẫn và viết lại kết luận cho "
    "đúng với nội dung đoạn đó."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse(raw: str) -> dict[str, bool] | None:
    """Pull the JSON verdict out of the model's reply, or ``None``."""
    match = _JSON_RE.search(raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _reason_from(data: dict[str, bool] | None) -> str | None:
    """Map a parsed verdict to the correction to send, or ``None`` if clean."""
    if not data:
        return None
    if data.get("them_tinh_tiet") is True:
        return _INVENTED_FACTS_REASON
    if data.get("nguoc_trich_dan") is True:
        return _CONTRADICTS_REASON
    return None


def _payload(question: str, answer: str) -> dict[str, object]:
    return {
        "model": settings.chat_model,
        "prompt": _VERIFY_PROMPT.format(question=question, answer=answer),
        "stream": False,
        "format": "json",
        "keep_alive": settings.ollama_keep_alive,
        # Deterministic and short: this is a classification, not prose.
        # num_ctx MUST match generator._ollama_payload's: a coverage turn
        # calls generate (num_ctx=llm_context_window) then this verifier
        # immediately after, on the SAME loaded llama.cpp instance. A
        # mismatched context size forces Ollama to fully reload the model
        # for the size change, not a no-op — found live, 2026-08-06, via
        # ~/.ollama/logs/server.log showing n_ctx_slot flip-flopping between
        # requests and correlating with intermittent 500s. Every coverage
        # turn already pays this twice (verify, then possibly re-verify
        # after a correction) even outside eval, so this was silently
        # inflating coverage-turn latency in production too.
        "options": {
            "temperature": 0.0,
            "num_predict": 64,
            "num_ctx": settings.llm_context_window,
        },
    }


def verify_answer(question: str, answer: str) -> str | None:
    """Correction to apply, or ``None`` when the answer looks clean.

    Fails open on any error — see the module docstring.
    """
    if not settings.coverage_llm_verify_enabled or not answer.strip():
        return None
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json=_payload(question, answer),
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        reason = _reason_from(_parse(resp.json().get("response", "")))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("coverage verifier unavailable, passing answer: %s", exc)
        return None
    if reason:
        logger.info("coverage verifier rejected the answer: %s", reason[:60])
    return reason


async def averify_answer(question: str, answer: str) -> str | None:
    """Async twin of ``verify_answer`` (the streaming path needs it)."""
    if not settings.coverage_llm_verify_enabled or not answer.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json=_payload(question, answer),
            )
            resp.raise_for_status()
            reason = _reason_from(_parse(resp.json().get("response", "")))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("coverage verifier unavailable, passing answer: %s", exc)
        return None
    if reason:
        logger.info("coverage verifier rejected the answer: %s", reason[:60])
    return reason


def verification_messages(
    messages: list[dict[str, str]], answer: str, reason: str
) -> list[dict[str, str]]:
    """``messages`` continued with the rejected answer and the verifier's note."""
    return [
        *messages,
        {"role": "assistant", "content": answer},
        {
            "role": "user",
            "content": (
                f"{reason}\n\nCHỈ xuất ra câu trả lời cuối cùng dành cho nhân "
                "viên. TUYỆT ĐỐI KHÔNG nhắc lại yêu cầu trong tin nhắn này."
            ),
        },
    ]
