"""Generation tests: context assembly, the 4 mandatory prompt properties, and
the pure message/SSE-building helpers in generator.py. No Ollama needed.
"""

from __future__ import annotations

import asyncio
import json

from app.config.settings import settings
from app.generation.generator import (
    ThinkStripper,
    _is_refusal,
    _ollama_payload,
    _sources_suffix,
    build_messages,
    parse_ollama_line,
    stream_static_answer,
    strip_think,
)
from app.generation.prompts import (
    REFUSAL_MESSAGE,
    SYSTEM_PROMPT,
    build_user_prompt,
    format_context,
    format_sources,
)
from app.models.schemas import ChatMessage, DocType, Hit, QdrantPayload


def _hit(doc_title: str, section_path: str, text: str, page: int | None = None) -> Hit:
    payload = QdrantPayload(
        doc_id="d1",
        doc_title=doc_title,
        section_path=section_path,
        page=page,
        doc_type=DocType.OTHER,
        display_text=text,
        chunk_index=0,
        ingested_at="2026-01-01T00:00:00+00:00",
    )
    return Hit(point_id="p1", score=1.0, payload=payload)


# --------------------------------------------------------------------------- #
# The 4 non-negotiable properties of SYSTEM_PROMPT (CLAUDE.md answering rules)
# --------------------------------------------------------------------------- #


def test_system_prompt_keeps_the_four_mandatory_properties() -> None:
    assert "CHỈ trả lời dựa trên nội dung" in SYSTEM_PROMPT
    assert "[Tên tài liệu, mục X]" in SYSTEM_PROMPT
    assert "Tôi không tìm thấy thông tin trong tài liệu" in SYSTEM_PROMPT
    assert (
        "Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức"
        in SYSTEM_PROMPT
    )


# --------------------------------------------------------------------------- #
# Context assembly
# --------------------------------------------------------------------------- #


def test_format_context_numbers_chunks_with_citation_header() -> None:
    hits = [
        _hit("Quy tắc An Tâm Bảo Vệ", "Chương II > Điều 5", "Nội dung điều 5."),
        _hit("Hướng dẫn dự phòng", "Điều 2", "Nội dung điều 2."),
    ]
    context = format_context(hits)
    assert "[1] Tài liệu: Quy tắc An Tâm Bảo Vệ > Chương II > Điều 5" in context
    assert "[2] Tài liệu: Hướng dẫn dự phòng > Điều 2" in context
    assert "Nội dung điều 5." in context
    assert "Nội dung điều 2." in context


def test_format_context_empty_hits_says_nothing_found() -> None:
    context = format_context([])
    assert "Không tìm thấy" in context


def test_build_user_prompt_includes_context_and_question() -> None:
    hits = [_hit("Tài liệu A", "Điều 1", "Nội dung.")]
    prompt = build_user_prompt("Phí thuần là gì?", hits)
    assert "Câu hỏi: Phí thuần là gì?" in prompt
    assert "[1] Tài liệu: Tài liệu A > Điều 1" in prompt


# --------------------------------------------------------------------------- #
# generator.py pure helpers
# --------------------------------------------------------------------------- #


def test_build_messages_includes_system_history_and_grounded_question() -> None:
    history = [
        ChatMessage(role="user", content="Phí thuần là gì?"),
        ChatMessage(role="assistant", content="Phí thuần là ..."),
    ]
    hits = [_hit("Tài liệu A", "Điều 1", "Nội dung.")]
    messages = build_messages("còn phí gộp?", hits, history)

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1] == {"role": "user", "content": "Phí thuần là gì?"}
    assert messages[2] == {"role": "assistant", "content": "Phí thuần là ..."}
    assert messages[-1]["role"] == "user"
    assert "còn phí gộp?" in messages[-1]["content"]
    assert "[1] Tài liệu: Tài liệu A > Điều 1" in messages[-1]["content"]


def test_build_messages_without_history() -> None:
    messages = build_messages("Phí thuần là gì?", [], None)
    assert len(messages) == 2  # system + the grounded user turn only
    assert messages[0]["role"] == "system"


def test_parse_ollama_line_extracts_content_and_done() -> None:
    line = json.dumps(
        {"message": {"role": "assistant", "content": "Xin chào"}, "done": False}
    )
    content, done = parse_ollama_line(line)
    assert content == "Xin chào"
    assert done is False


def test_parse_ollama_line_final_chunk() -> None:
    line = json.dumps({"message": {"role": "assistant", "content": ""}, "done": True})
    content, done = parse_ollama_line(line)
    assert content == ""
    assert done is True


# --------------------------------------------------------------------------- #
# <think> stripping (reasoning models must never leak chain-of-thought)
# --------------------------------------------------------------------------- #


def test_refusal_message_constant_matches_system_prompt() -> None:
    # The deterministic-refusal path and the prompt must agree on the sentence.
    assert REFUSAL_MESSAGE.rstrip(".") in SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# Sources block ("Nguồn tham khảo")
# --------------------------------------------------------------------------- #


def test_format_sources_numbers_match_context_and_dedupes() -> None:
    hits = [
        _hit("Quy tắc An Tâm", "Điều 5", "A", page=3),
        _hit("Quy tắc An Tâm", "Điều 5", "B", page=3),  # same doc+section: once
        _hit("Hướng dẫn dự phòng", "Điều 2", "C"),
    ]
    block = format_sources(hits)
    assert "**Nguồn tham khảo:**" in block
    assert "- [1] Quy tắc An Tâm — Điều 5 (trang 3)" in block
    assert "[2]" not in block  # deduped, and numbering keeps context indices
    assert "- [3] Hướng dẫn dự phòng — Điều 2" in block


def test_format_sources_empty_hits() -> None:
    assert format_sources([]) == ""


def test_sources_suffix_appended_to_normal_answers() -> None:
    hits = [_hit("Tài liệu A", "Điều 1", "Nội dung.")]
    suffix = _sources_suffix("Phí thuần là ... [Tài liệu A, Điều 1]", hits)
    assert suffix.startswith("\n\n**Nguồn tham khảo:**")


def test_sources_suffix_skipped_for_refusals_and_empty() -> None:
    hits = [_hit("Tài liệu A", "Điều 1", "Nội dung.")]
    assert _sources_suffix(REFUSAL_MESSAGE, hits) == ""
    assert _sources_suffix("", hits) == ""
    assert _sources_suffix("Câu trả lời.", []) == ""


def test_is_refusal_matches_with_and_without_trailing_period() -> None:
    assert _is_refusal(REFUSAL_MESSAGE)
    assert _is_refusal("Tôi không tìm thấy thông tin trong tài liệu")
    assert not _is_refusal("Phí thuần là ...")


# --------------------------------------------------------------------------- #
# Ollama payload + deterministic refusal streaming
# --------------------------------------------------------------------------- #


def test_ollama_payload_sends_keep_alive() -> None:
    payload = _ollama_payload([{"role": "user", "content": "hi"}], stream=True)
    assert payload["keep_alive"] == settings.ollama_keep_alive


def _collect_sse_content(chunks: list[str]) -> str:
    text = ""
    for chunk in chunks:
        payload = chunk.removeprefix("data: ").strip()
        if not payload or payload == "[DONE]":
            continue
        delta = json.loads(payload)["choices"][0]["delta"]
        text += delta.get("content", "")
    return text


def test_stream_static_answer_is_valid_openai_sse() -> None:
    async def collect() -> list[str]:
        return [chunk async for chunk in stream_static_answer(REFUSAL_MESSAGE)]

    chunks = asyncio.run(collect())
    assert chunks[-1] == "data: [DONE]\n\n"
    assert _collect_sse_content(chunks) == REFUSAL_MESSAGE
    finish_reasons = [
        json.loads(c.removeprefix("data: "))["choices"][0]["finish_reason"]
        for c in chunks[:-1]
    ]
    assert finish_reasons[-1] == "stop"


def test_strip_think_removes_full_block() -> None:
    text = "<think>reasoning here</think>\n\nPhí thuần là ... [1]"
    assert strip_think(text) == "Phí thuần là ... [1]"


def test_strip_think_passthrough_when_no_tags() -> None:
    assert strip_think("Câu trả lời bình thường.") == "Câu trả lời bình thường."


def _feed_all(stripper: ThinkStripper, deltas: list[str]) -> str:
    return "".join(stripper.feed(d) for d in deltas) + stripper.flush()


def test_think_stripper_streaming_drops_reasoning() -> None:
    deltas = ["<think>", "suy ", "luận", "</think>", "Đáp ", "án [1]"]
    assert _feed_all(ThinkStripper(), deltas) == "Đáp án [1]"


def test_think_stripper_handles_tag_split_across_deltas() -> None:
    # Opening/closing tags arrive in fragments spanning multiple deltas.
    deltas = ["<thi", "nk>hidden</thi", "nk>Kết quả cuối"]
    assert _feed_all(ThinkStripper(), deltas) == "Kết quả cuối"


def test_think_stripper_without_any_think_tags() -> None:
    deltas = ["Phí ", "thuần ", "là gì"]
    assert _feed_all(ThinkStripper(), deltas) == "Phí thuần là gì"


def test_think_stripper_unclosed_think_is_dropped() -> None:
    # If generation ends mid-reasoning, emit nothing rather than raw thoughts.
    deltas = ["<think>đang nghĩ dở"]
    assert _feed_all(ThinkStripper(), deltas) == ""
