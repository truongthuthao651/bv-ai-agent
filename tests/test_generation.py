"""Generation tests: context assembly, the 4 mandatory prompt properties, and
the pure message/SSE-building helpers in generator.py. No Ollama needed.
"""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import quote

from app.config.settings import settings
from app.generation.generator import (
    ThinkStripper,
    _advisory_disclaimer_suffix,
    _disclaimer_suffix,
    _general_knowledge_suffix,
    _hybrid_disclaimer_suffix,
    _is_refusal,
    _ollama_payload,
    _sources_suffix,
    build_hybrid_messages,
    build_messages,
    parse_ollama_line,
    stream_static_answer,
    strip_think,
)
from app.generation.prompts import (
    ADVISORY_DISCLAIMER,
    ADVISORY_SYSTEM_PROMPT,
    CALC_DISCLAIMER,
    GENERAL_KNOWLEDGE_DISCLAIMER,
    GENERAL_KNOWLEDGE_HEADING,
    HYBRID_DISCLAIMER,
    HYBRID_SYSTEM_PROMPT,
    REFUSAL_MESSAGE,
    SYSTEM_PROMPT,
    build_user_prompt,
    format_context,
    format_sources,
    system_prompt,
)
from app.models.schemas import ChatMessage, DocType, Hit, QdrantPayload


def _hit(
    doc_title: str,
    section_path: str,
    text: str,
    page: int | None = None,
    source_filename: str | None = None,
    source_url: str | None = None,
    parent_text: str | None = None,
) -> Hit:
    payload = QdrantPayload(
        doc_id="d1",
        doc_title=doc_title,
        section_path=section_path,
        page=page,
        doc_type=DocType.OTHER,
        display_text=text,
        parent_text=parent_text,
        parent_index=0 if parent_text else None,
        chunk_index=0,
        source_filename=source_filename,
        source_url=source_url,
        ingested_at="2026-01-01T00:00:00+00:00",
    )
    return Hit(point_id="p1", score=1.0, payload=payload)


# --------------------------------------------------------------------------- #
# The 4 non-negotiable properties of SYSTEM_PROMPT (CLAUDE.md answering rules)
# --------------------------------------------------------------------------- #


def test_system_prompt_keeps_the_four_mandatory_properties() -> None:
    assert "CHỈ trả lời dựa trên nội dung" in SYSTEM_PROMPT
    assert "trích dẫn nguồn bằng SỐ của đoạn ngữ cảnh" in SYSTEM_PROMPT
    assert "Tôi không tìm thấy thông tin trong tài liệu" in SYSTEM_PROMPT
    assert (
        "Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức"
        in SYSTEM_PROMPT
    )


def test_system_prompt_forbids_inverting_exclusions() -> None:
    # Small local models often flip "loại trừ" into "được bảo hiểm"; the prompt
    # must explicitly ban that polarity error (observed on skiing/diving Qs).
    assert "LOẠI TRỪ" in SYSTEM_PROMPT
    assert "đảo chiều polar" in SYSTEM_PROMPT or "TUYỆT ĐỐI không" in SYSTEM_PROMPT
    assert "trượt tuyết" in SYSTEM_PROMPT  # concrete exclusion example anchored


def test_system_prompt_forbids_overapplying_exclusions() -> None:
    # The reverse failure of the polarity rule (observed on a traffic-accident
    # question): the model concluded "không được bồi thường" from exclusions
    # whose conditions ("lỗi cố ý", "hành vi phạm tội") did not match the
    # scenario, and invented a new exclusion ("tai nạn xe không thuộc phạm vi
    # bảo hiểm"). The prompt must ban applying an exclusion to a non-matching
    # event and ban inventing exclusions absent from the context.
    assert "CHỈ VÌ ngữ cảnh có mục loại trừ" in SYSTEM_PROMPT
    assert "KHÔNG nằm trong danh sách loại trừ" in SYSTEM_PROMPT
    assert "bịa thêm loại trừ" in SYSTEM_PROMPT
    # When no exclusion matches and the payout amount is absent, the model must
    # say the document doesn't state it — not assert covered/not-covered.
    assert "tài liệu không nêu mức chi trả cụ thể" in SYSTEM_PROMPT


def test_system_prompt_numbers_its_rules_in_order() -> None:
    # Assembled from shared blocks, so a reordering can leave the visible
    # numbering out of sequence.
    positions = [SYSTEM_PROMPT.index(f"\n{n}. ") for n in range(1, 8)]
    assert positions == sorted(positions)


def test_prompt_never_points_at_a_rule_by_number() -> None:
    # The model copies the prompt's wording: "trả lời theo quy tắc 3" came back
    # verbatim to the employee as "Trả lời theo quy tắc 3: Tôi không tìm thấy
    # thông tin trong tài liệu." (golden fr02) — leaking internals and refusing
    # after it had already answered. Rules must state what to do, not point at a
    # number. The single allowed mention is the line forbidding exactly this.
    allowed = 'kể cả số hiệu quy tắc (ví dụ "theo quy tắc 3")'
    for advisory in (False, True):
        prompt = system_prompt(advisory=advisory)
        assert allowed in prompt
        assert not re.findall(r"quy tắc \d", prompt.replace(allowed, ""))


def test_refusal_sentence_is_written_out_only_once() -> None:
    # Rules 1 and 6 name the refusal ("CÂU TỪ CHỐI BẮT BUỘC") instead of quoting
    # it. Spelling it out three times made refusal salient enough to flip an
    # answerable question (golden q29_en) into a refusal.
    for advisory in (False, True):
        assert system_prompt(advisory=advisory).count(REFUSAL_MESSAGE.rstrip(".")) == 1


def test_refusal_sentence_is_the_whole_answer_or_absent() -> None:
    # Answering and then appending the refusal is self-contradictory (fr02).
    for advisory in (False, True):
        assert "TOÀN BỘ câu trả lời khi dùng" in system_prompt(advisory=advisory)


def test_system_prompt_forbids_remapping_interest_to_claim_percent() -> None:
    assert "Lãi suất cam kết" in SYSTEM_PROMPT
    assert "tỷ lệ bồi thường" in SYSTEM_PROMPT
    assert (
        "Không ĐỔI LOẠI CHỈ SỐ" in SYSTEM_PROMPT or "ĐỔI LOẠI CHỈ SỐ" in SYSTEM_PROMPT
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


def test_format_context_widens_a_child_to_its_parent_window() -> None:
    # Retrieval matched a narrow passage; the model must still see the
    # surrounding conditions it was cut from (parent-child chunking).
    parent = (
        "Điều kiện chi trả quyền lợi tử vong.\n\n"
        "Công ty chi trả 100% số tiền bảo hiểm.\n\n"
        "Trong đó số tiền bảo hiểm là mệnh giá ghi trên hợp đồng."
    )
    hits = [
        _hit(
            "Quy tắc An Tâm Bảo Vệ",
            "Điều 5",
            "Công ty chi trả 100% số tiền bảo hiểm.",
            parent_text=parent,
        )
    ]
    context = format_context(hits)
    assert "Điều kiện chi trả quyền lợi tử vong." in context
    assert "mệnh giá ghi trên hợp đồng" in context


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

    # The system turn is the assembled strict prompt (SYSTEM_PROMPT plus the
    # optional general-knowledge block when that setting is on).
    assert messages[0] == {"role": "system", "content": system_prompt()}
    assert messages[0]["content"].startswith(SYSTEM_PROMPT.split("\n")[0])
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
# Hybrid (no-context, general-knowledge) fallback
# --------------------------------------------------------------------------- #


def test_hybrid_system_prompt_still_requires_refusal_for_company_specifics() -> None:
    # A SEPARATE, weaker prompt from SYSTEM_PROMPT — but it must still keep the
    # refusal rule for anything company-specific it can't actually know.
    assert REFUSAL_MESSAGE.rstrip(".") in HYBRID_SYSTEM_PROMPT
    assert HYBRID_SYSTEM_PROMPT != SYSTEM_PROMPT


def test_build_hybrid_messages_has_no_retrieved_context() -> None:
    history = [ChatMessage(role="user", content="Phí thuần là gì?")]
    messages = build_hybrid_messages("còn phí gộp?", history)
    assert messages[0] == {"role": "system", "content": HYBRID_SYSTEM_PROMPT}
    assert messages[-1] == {"role": "user", "content": "còn phí gộp?"}


def test_hybrid_disclaimer_appended_to_general_knowledge_answers() -> None:
    suffix = _hybrid_disclaimer_suffix("Phí thuần là phần phí ...")
    assert HYBRID_DISCLAIMER in suffix


def test_hybrid_disclaimer_skipped_for_refusals_and_empty() -> None:
    assert _hybrid_disclaimer_suffix(REFUSAL_MESSAGE) == ""
    assert _hybrid_disclaimer_suffix("") == ""


def test_hybrid_disclaimer_not_duplicated() -> None:
    answer = f"Phí thuần là ... {HYBRID_DISCLAIMER}"
    assert _hybrid_disclaimer_suffix(answer) == ""


# --------------------------------------------------------------------------- #
# Advisory / synthesis prompt variant
# --------------------------------------------------------------------------- #


def test_advisory_prompt_keeps_every_non_negotiable_property() -> None:
    # Advisory mode widens *reasoning*, never sourcing: the refusal sentence,
    # the citation format, the wrong-product ban, the calc disclaimer, the
    # exclusion rules and the metric rule must all survive verbatim.
    assert REFUSAL_MESSAGE.rstrip(".") in ADVISORY_SYSTEM_PROMPT
    assert "trích dẫn nguồn bằng SỐ của đoạn ngữ cảnh" in ADVISORY_SYSTEM_PROMPT
    assert "trích dẫn theo định dạng [n]" in ADVISORY_SYSTEM_PROMPT
    assert (
        "TUYỆT ĐỐI không trả lời thay bằng nội dung của một sản phẩm khác"
        in ADVISORY_SYSTEM_PROMPT
    )
    assert CALC_DISCLAIMER.rstrip(".") in ADVISORY_SYSTEM_PROMPT
    assert "LOẠI TRỪ" in ADVISORY_SYSTEM_PROMPT
    assert "CHỈ VÌ ngữ cảnh có mục loại trừ" in ADVISORY_SYSTEM_PROMPT
    assert "Lãi suất cam kết" in ADVISORY_SYSTEM_PROMPT


def test_advisory_prompt_permits_synthesis_that_strict_prompt_forbids() -> None:
    assert ADVISORY_SYSTEM_PROMPT != SYSTEM_PROMPT
    # Strict forbids anything outside the context outright...
    assert "Không dùng kiến thức bên ngoài ngữ cảnh" in SYSTEM_PROMPT
    # ...advisory instead requires every DATUM to come from context while
    # allowing conclusions to be drawn across those data.
    assert "ĐƯỢC PHÉP suy luận và tổng hợp" in ADVISORY_SYSTEM_PROMPT
    assert "phù hợp với nhu cầu nào" in ADVISORY_SYSTEM_PROMPT
    # And it must not let a partly-covered comparison collapse into a refusal.
    assert "KHÔNG được từ chối toàn bộ" in ADVISORY_SYSTEM_PROMPT
    # Recommendations stay conditional and internal-facing.
    assert "không dùng ngôn ngữ chào bán" in ADVISORY_SYSTEM_PROMPT


def test_build_messages_selects_prompt_variant() -> None:
    hits = [_hit("Tài liệu A", "Điều 1", "Nội dung.")]
    strict = build_messages("so sánh?", hits, None, advisory=False)
    advisory = build_messages("so sánh?", hits, None, advisory=True)
    assert strict[0]["content"] == system_prompt(advisory=False)
    assert advisory[0]["content"] == system_prompt(advisory=True)
    assert strict[0]["content"] != advisory[0]["content"]
    # The retrieved context is identical — only the instructions differ.
    assert strict[-1] == advisory[-1]


def test_advisory_disclaimer_appended_labeled_and_not_duplicated() -> None:
    suffix = _advisory_disclaimer_suffix("Sản phẩm A phù hợp nếu ...")
    assert ADVISORY_DISCLAIMER in suffix
    assert _advisory_disclaimer_suffix(f"... {ADVISORY_DISCLAIMER}") == ""
    assert _advisory_disclaimer_suffix(REFUSAL_MESSAGE) == ""
    assert _advisory_disclaimer_suffix("") == ""


# --------------------------------------------------------------------------- #
# Optional general-knowledge supplement
# --------------------------------------------------------------------------- #


def test_general_knowledge_block_is_opt_in_via_settings() -> None:
    with_block = system_prompt(general_knowledge=True)
    without = system_prompt(general_knowledge=False)
    assert GENERAL_KNOWLEDGE_HEADING in with_block
    assert GENERAL_KNOWLEDGE_HEADING not in without
    assert without == SYSTEM_PROMPT
    # It may never displace the grounded answer, nor carry company specifics.
    assert "KHÔNG BAO GIỜ thay thế phần trả lời dựa trên ngữ cảnh" in with_block
    assert "KHÔNG trích dẫn nguồn [n]" in with_block


def test_general_knowledge_label_added_only_when_the_section_is_present() -> None:
    plain = "Quyền lợi tử vong là 100% STBH [Quy tắc A, Điều 5]."
    assert _general_knowledge_suffix(plain) == ""
    mixed = f"{plain}\n\n{GENERAL_KNOWLEDGE_HEADING}\nBảo hiểm hỗn hợp là ..."
    assert GENERAL_KNOWLEDGE_DISCLAIMER in _general_knowledge_suffix(mixed)
    # Not duplicated, and never attached to a refusal.
    assert _general_knowledge_suffix(f"{mixed}\n{GENERAL_KNOWLEDGE_DISCLAIMER}") == ""
    assert _general_knowledge_suffix(REFUSAL_MESSAGE) == ""


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
    base = settings.api_public_base_url
    # Citation links now target the scrollable viewer, deep-linked to the cited
    # section via a URL-encoded ?section= query.
    sec5 = quote("Điều 5", safe="")
    # Page is carried in the link too, so a native PDF opens at the cited page.
    link = f"[Quy tắc An Tâm]({base}/documents/d1/view?section={sec5}&page=3)"
    assert f"- [1] {link} — Điều 5 (trang 3)" in block
    # The duplicate shares [1] rather than consuming [2]: numbering stays
    # contiguous, so the third source is [2] here AND [2] in the context.
    sec2 = quote("Điều 2", safe="")
    link2 = f"[Hướng dẫn dự phòng]({base}/documents/d1/view?section={sec2})"
    assert f"- [2] {link2} — Điều 2" in block
    assert "[3]" not in block


def test_every_context_number_resolves_to_a_source_line() -> None:
    """The citation contract: no marker the model can copy is a dead link.

    Enumerating context and sources independently broke this — a duplicated
    (doc, section) consumed a context number that the deduped sources block
    never listed, so a model citing it sent the employee to nothing. Under
    parent-child chunking, two children of one parent are exactly that case.
    """
    hits = [
        _hit("Quy tắc An Tâm", "Điều 5", "child A"),
        _hit("Quy tắc An Tâm", "Điều 5", "child B"),  # same parent section
        _hit("Hướng dẫn dự phòng", "Điều 2", "C"),
        _hit("Quy tắc An Tâm", "Điều 9", "D"),
    ]
    context_numbers = set(
        re.findall(r"^\[(\d+)\] Tài liệu:", format_context(hits), re.M)
    )
    source_numbers = set(re.findall(r"^- \[(\d+)\]", format_sources(hits), re.M))
    assert context_numbers == source_numbers == {"1", "2", "3"}


def test_format_sources_links_pdf_straight_to_original_file_at_page() -> None:
    # A PDF the browser renders inline: link to the original upload, not the
    # reconstructed viewer, deep-linked to the cited page via #page=N.
    hits = [_hit("Quy tắc An Tâm", "Điều 5", "A", page=7, source_filename="an_tam.pdf")]
    block = format_sources(hits)
    base = settings.api_public_base_url
    link = f"[Quy tắc An Tâm]({base}/documents/d1/file#page=7)"
    assert f"- [1] {link} — Điều 5 (trang 7)" in block
    assert "/view?" not in block  # never the rewritten viewer for a PDF original


def test_format_sources_links_image_to_original_without_page_fragment() -> None:
    hits = [_hit("Ảnh scan", "(toàn văn)", "A", page=1, source_filename="scan.png")]
    block = format_sources(hits)
    base = settings.api_public_base_url
    assert f"[Ảnh scan]({base}/documents/d1/file)" in block
    assert "#page=" not in block  # images have no pages


def test_format_sources_falls_back_to_viewer_for_non_inline_original() -> None:
    # DOCX can't render inline in a browser, so keep the reconstructed viewer.
    sec = quote("Điều 2", safe="")
    hits = [_hit("Quy trình", "Điều 2", "A", page=2, source_filename="quy_trinh.docx")]
    block = format_sources(hits)
    base = settings.api_public_base_url
    assert f"{base}/documents/d1/view?section={sec}&page=2" in block


def test_format_sources_links_knowledge_pack_to_its_public_url() -> None:
    # Knowledge-pack material cites the public original it was downloaded from,
    # labeled so it's never mistaken for an internal company document.
    url = "https://vanban.example.gov.vn/luat-08-2022-qh15"
    hits = [
        _hit(
            "Luật Kinh doanh bảo hiểm 2022",
            "Điều 12",
            "A",
            page=4,
            source_filename="luat.pdf",
            source_url=url,
        )
    ]
    block = format_sources(hits)
    assert f"- [1] [Luật Kinh doanh bảo hiểm 2022]({url}) — Điều 12" in block
    assert "(nguồn công khai)" in block
    assert "(trang 4)" in block
    # The public URL wins over the internal viewer/file link entirely.
    assert settings.api_public_base_url + "/documents/d1" not in block


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


def test_calc_disclaimer_constant_matches_system_prompt() -> None:
    # The guardrail and the prompt must agree on the exact sentence.
    assert CALC_DISCLAIMER.rstrip(".") in SYSTEM_PROMPT


def test_disclaimer_appended_to_numeric_answers() -> None:
    answer = "Với $i = 0,05$: $v \\approx 0,952$ [Tài liệu, Điều 3]"
    assert _disclaimer_suffix(answer) == f"\n\n{CALC_DISCLAIMER}"


def test_disclaimer_triggers_on_numeric_substitution_without_approx() -> None:
    answer = "Thay số: $P = 750000000 \\cdot 0,0042$ [Tài liệu, Điều 5]"
    assert _disclaimer_suffix(answer) == f"\n\n{CALC_DISCLAIMER}"


def test_disclaimer_not_duplicated_when_model_already_included_it() -> None:
    answer = f"$v \\approx 0,952$. {CALC_DISCLAIMER}"
    assert _disclaimer_suffix(answer) == ""


def test_disclaimer_skipped_for_pure_formulas_and_cited_figures() -> None:
    # Structural constants ($1$ in the identity) are not computed results.
    assert (
        _disclaimer_suffix("$A_x = 1 - d \\cdot \\ddot{a}_x$ [Tài liệu, Điều 3]") == ""
    )
    # Plain-text figures quoted from a document are citations, not arithmetic.
    assert _disclaimer_suffix("Thời gian gia hạn là 60 ngày. [Tài liệu, Điều 6]") == ""
    assert _disclaimer_suffix(REFUSAL_MESSAGE) == ""
    assert _disclaimer_suffix("") == ""


def test_ollama_payload_sends_keep_alive() -> None:
    payload = _ollama_payload([{"role": "user", "content": "hi"}], stream=True)
    assert payload["keep_alive"] == settings.ollama_keep_alive


def test_ollama_payload_sends_context_window() -> None:
    # Without num_ctx Ollama loads the model at its (small) modelfile default and
    # silently context-shifts away the retrieved chunks — an invisible grounding
    # failure. It must carry settings.llm_context_window.
    payload = _ollama_payload([{"role": "user", "content": "hi"}], stream=False)
    assert payload["options"]["num_ctx"] == settings.llm_context_window


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
