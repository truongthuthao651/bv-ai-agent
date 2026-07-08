"""Generation tests: context assembly, the 4 mandatory prompt properties, and
the pure message/SSE-building helpers in generator.py. No Ollama needed.
"""

from __future__ import annotations

import json

from app.generation.generator import build_messages, parse_ollama_line
from app.generation.prompts import SYSTEM_PROMPT, build_user_prompt, format_context
from app.models.schemas import ChatMessage, DocType, Hit, QdrantPayload


def _hit(doc_title: str, section_path: str, text: str) -> Hit:
    payload = QdrantPayload(
        doc_id="d1",
        doc_title=doc_title,
        section_path=section_path,
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
