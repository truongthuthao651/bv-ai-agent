"""Coverage-guard tests: question detection, benefit expansion, exclusion-only context.

Pure functions only — no Qdrant, no Ollama. The failure these encode was
observed on a real policy PDF (2026-07-27): retrieval returned a single
exclusion section, and the answer denied the claim by applying a
substandard-health underwriting clause to an ordinary car accident.
"""

from __future__ import annotations

from app.generation.prompts import GENERAL_KNOWLEDGE_HEADING, system_prompt
from app.models.schemas import ChatMessage, DocType, Hit, QdrantPayload
from app.retrieval.coverage import (
    backfill_payout_clause,
    expand_coverage_query,
    grants_a_benefit,
    is_coverage_question,
    is_coverage_thread,
    no_payout_clause_retrieved,
    payout_clauses_first,
)


def _hit(section_path: str, text: str) -> Hit:
    payload = QdrantPayload(
        doc_id="d1",
        doc_title="Quy tắc sản phẩm",
        section_path=section_path,
        page=None,
        doc_type=DocType.POLICY,
        display_text=text,
        chunk_index=0,
        ingested_at="2026-01-01T00:00:00+00:00",
    )
    # Distinct ids: the backfill dedupes on point_id, so a shared one would make
    # every fixture hit look like a duplicate of every other.
    return Hit(
        point_id=f"p-{abs(hash(section_path)) % 10**8}", score=1.0, payload=payload
    )


def test_detects_coverage_questions_including_the_reported_one() -> None:
    assert is_coverage_question(
        "nếu tôi mua bảo hiểm An Phú Liên Kết và bị tai nạn xe khi đi du lịch "
        "thì có được claim không?"
    )
    assert is_coverage_question("bị tai nạn giao thông có được chi trả không?")
    assert is_coverage_question("nằm viện do bệnh có được bảo hiểm không?")
    assert is_coverage_question("Am I covered if I have an accident?")


def test_does_not_fire_on_other_question_shapes() -> None:
    # Amount questions are the metric guard's business; definitions and
    # procedures must keep their unmodified query.
    assert not is_coverage_question("Quyền lợi tử vong là bao nhiêu phần trăm?")
    assert not is_coverage_question("Phí thuần được tính như thế nào?")
    assert not is_coverage_question("Hồ sơ yêu cầu bồi thường gồm những gì?")
    assert not is_coverage_question("")


def test_expansion_adds_benefit_terms_only_for_coverage_questions() -> None:
    q = "bị tai nạn xe có được chi trả không?"
    expanded = expand_coverage_query(q)
    assert q in expanded
    assert "quyền lợi bảo hiểm" in expanded
    assert "phạm vi bảo hiểm" in expanded
    other = "Phí ban đầu là bao nhiêu?"
    assert expand_coverage_query(other) == other


def test_benefit_detection_keys_on_the_payout_side_not_the_denial_side() -> None:
    # Grants a benefit.
    assert grants_a_benefit(
        _hit("Chương II > Điều 3: Quyền lợi tử vong", "Công ty chi trả 100% STBH.")
    )
    assert grants_a_benefit(
        _hit("Điều 12", "Công ty chi trả sau khi trừ phí còn thiếu.")
    )
    # Denial framing must not read as a grant: the negation sits between the two
    # halves of the folded phrase ("cong ty khong chi tra").
    assert not grants_a_benefit(
        _hit(
            "Điều 7: Các trường hợp loại trừ chung",
            "Công ty không chi trả bất kỳ quyền lợi nào nếu...",
        )
    )
    # Articles that LOOK like benefit headings but grant nothing — the three the
    # first (exclusion-vocabulary) design missed on the grown corpus.
    assert not grants_a_benefit(
        _hit(
            "Điều 6: Các quyền lợi không thuộc sản phẩm chính",
            "... chỉ phát sinh khi tham gia sản phẩm bổ trợ.",
        )
    )
    assert not grants_a_benefit(
        _hit(
            "Điều 9: Thời gian chờ đối với quyền lợi liên quan đến bệnh tật",
            "Công ty không chi trả trong 30 ngày...",
        )
    )
    assert not grants_a_benefit(
        _hit(
            "Điều 15: Hồ sơ yêu cầu giải quyết quyền lợi",
            "Hồ sơ bao gồm: Giấy yêu cầu...",
        )
    )


def test_backfill_fetches_a_payout_clause_from_the_same_documents() -> None:
    exclusion = _hit(
        "Điều 7: Các trường hợp loại trừ chung", "Công ty không chi trả..."
    )
    benefit = _hit("Điều 3: Quyền lợi tử vong", "Công ty chi trả 100% STBH.")
    paperwork = _hit("Điều 15: Hồ sơ", "Hồ sơ gồm...")
    calls: list[tuple[str, list[str]]] = []

    def search_fn(query: str, doc_ids: list[str]) -> list[Hit]:
        calls.append((query, doc_ids))
        return [paperwork, benefit]  # only the benefit clause qualifies

    out = backfill_payout_clause([exclusion], search_fn=search_fn)
    assert out[0] is exclusion
    assert benefit in out
    assert paperwork not in out
    # Scoped to the documents already matched, so it cannot pull in another
    # product's benefit article.
    assert calls[0][1] == ["d1"]
    assert not no_payout_clause_retrieved(out)


def test_backfill_evicts_the_weakest_noise_once_the_context_is_full() -> None:
    """Reported turn 3: appending grew a 5-hit budget to 7 and let junk in.

    Rerank order puts the weakest last, so the marketing figure and the
    footnote are what a benefit clause displaces — never another benefit, and
    never the exclusions while there is room.
    """
    excl = _hit("Điều 7: Loại trừ", "Công ty không chi trả...")
    waiting = _hit("Điều 9: Thời gian chờ", "...")
    paperwork = _hit("Điều 15: Hồ sơ", "...")
    marketing = _hit("Hơn 131.000 tỷ đồng", "...")
    footnote = _hit("Chú thích", "...")
    benefit = _hit("Điều 3: Quyền lợi tử vong", "Công ty chi trả 100% STBH.")
    death = _hit("Điều 4: Quyền lợi thương tật", "Công ty chi trả 100% STBH.")

    full = [excl, waiting, paperwork, marketing, footnote]
    out = backfill_payout_clause(
        full, search_fn=lambda q, ids: [benefit, death], budget=5
    )
    assert len(out) == 5
    assert benefit in out and death in out
    # The two weakest non-benefit hits went, the exclusions stayed.
    assert marketing not in out and footnote not in out
    assert out[:3] == [excl, waiting, paperwork]


def test_backfill_appends_while_there_is_room_in_the_budget() -> None:
    excl = _hit("Điều 7: Loại trừ", "Công ty không chi trả...")
    benefit = _hit("Điều 3: Quyền lợi tử vong", "Công ty chi trả 100% STBH.")
    out = backfill_payout_clause([excl], search_fn=lambda q, ids: [benefit], budget=5)
    # A thin context keeps its exclusions — they still have to be applied.
    assert out == [excl, benefit]


def test_backfill_is_a_no_op_when_nothing_qualifies() -> None:
    exclusion = _hit(
        "Điều 7: Các trường hợp loại trừ chung", "Công ty không chi trả..."
    )
    out = backfill_payout_clause([exclusion], search_fn=lambda q, d: [])
    assert out == [exclusion]
    # Documents genuinely silent on coverage: the prompt guard still has to fire.
    assert no_payout_clause_retrieved(out)


def test_backfill_never_duplicates_a_hit_already_in_context() -> None:
    benefit = _hit("Điều 3: Quyền lợi tử vong", "Công ty chi trả 100% STBH.")
    out = backfill_payout_clause([benefit], search_fn=lambda q, d: [benefit])
    assert out == [benefit]


def test_payout_clauses_lead_the_context_without_dropping_anything() -> None:
    # The model cites what it reads first: with the exclusions page at rank 1 it
    # cited only that and denied a covered death, leaving the benefit clause in
    # its own context uncited (real-doc failure, 2026-07-27).
    excl = _hit("Điều 7: Các trường hợp loại trừ chung", "Công ty không chi trả...")
    benefit = _hit("Điều 3: Quyền lợi tử vong", "Công ty chi trả 100% STBH.")
    waiting = _hit("Điều 9: Thời gian chờ", "Công ty không chi trả trong 30 ngày...")
    disability = _hit("Điều 4: Quyền lợi thương tật", "Công ty chi trả 100% STBH.")

    out = payout_clauses_first([excl, benefit, waiting, disability])
    assert out[:2] == [benefit, disability]  # benefits first, order preserved
    assert out[2:] == [excl, waiting]  # everything else kept, order preserved
    assert len(out) == 4  # nothing dropped: exclusions still have to be applied


def test_prompt_bans_reading_the_exclusion_list_as_a_coverage_list() -> None:
    # Rule 6(c). The observed inversion: "tử vong không được liệt kê trong danh
    # sách các loại rủi ro được bảo hiểm trong mục Loại trừ" -> denial.
    for advisory in (False, True):
        prompt = system_prompt(advisory=advisory, general_knowledge=False)
        assert "KHÔNG PHẢI LÀ DANH SÁCH RỦI RO ĐƯỢC BẢO HIỂM" in prompt
        assert "KHÔNG BỊ LOẠI TRỪ" in prompt


def test_no_payout_clause_is_the_state_that_forbids_denial() -> None:
    exclusion = _hit(
        "Điều 7: Các trường hợp loại trừ chung", "Công ty không chi trả..."
    )
    waiting = _hit("Điều 9: Thời gian chờ", "Công ty không chi trả trong 30 ngày...")
    paperwork = _hit("Điều 15: Hồ sơ yêu cầu giải quyết quyền lợi", "Hồ sơ gồm...")
    benefit = _hit("Điều 3: Quyền lợi tử vong", "Công ty chi trả 100% STBH.")
    assert no_payout_clause_retrieved([exclusion])
    # The real shape this guard exists for: nothing here is named "loại trừ"
    # except one article, yet no clause anywhere says when the Company pays.
    assert no_payout_clause_retrieved([exclusion, waiting, paperwork])
    # One payout clause is enough to make a grounded conclusion possible.
    assert not no_payout_clause_retrieved([exclusion, waiting, benefit])
    assert not no_payout_clause_retrieved([])


def test_prompt_gains_the_shape_rule_and_the_denial_ban_only_when_asked() -> None:
    plain = system_prompt(general_knowledge=False)
    shaped = system_prompt(coverage=True, general_knowledge=False)
    guarded = system_prompt(coverage_undetermined=True, general_knowledge=False)

    assert "CÓ ĐƯỢC CHI TRẢ KHÔNG" not in plain
    assert "CÓ ĐƯỢC CHI TRẢ KHÔNG" in shaped
    # The denial ban implies the shape rule — an undetermined answer still has
    # to be laid out as cases.
    assert "CÓ ĐƯỢC CHI TRẢ KHÔNG" in guarded
    assert "TUYỆT ĐỐI KHÔNG kết luận" in guarded
    assert "TUYỆT ĐỐI KHÔNG kết luận" not in shaped
    assert "TUYỆT ĐỐI KHÔNG kết luận" not in plain


class TestStickyCoverageThread:
    """Follow-ups carry no marker of their own; coverage-ness must stick.

    Verified against the reported conversation: both follow-ups scored False on
    ``is_coverage_question``, so the guard reached them only when the LLM
    rewrite happened to reinsert a marker.
    """

    def _thread(self) -> list[ChatMessage]:
        return [
            ChatMessage(
                role="user",
                content=(
                    "Nếu tôi mua sản phẩm an khang như ý và bị tai nạn xe khi "
                    "đi du lịch thì tôi có được claim không"
                ),
            ),
            ChatMessage(role="assistant", content="Không được claim."),
        ]

    def test_a_bare_event_followup_inherits_coverage(self) -> None:
        assert not is_coverage_question("tai nạn xe tử vong cơ mà")
        assert is_coverage_thread("tai nạn xe tử vong cơ mà", self._thread())

    def test_a_pushback_followup_inherits_coverage(self) -> None:
        q = "nhưng tôi đi đường bị người khác đâm mà"
        assert not is_coverage_question(q)
        assert is_coverage_thread(q, self._thread())

    def test_plural_nhung_is_not_read_as_the_pushback_nhung(self) -> None:
        """Folded, "những" and "nhưng" collide — and "những" is everywhere."""
        assert not is_coverage_thread("những sản phẩm nào đang bán?", self._thread())

    def test_an_unrelated_followup_does_not_inherit(self) -> None:
        assert not is_coverage_thread("phí đóng hàng năm là bao nhiêu?", self._thread())

    def test_nothing_sticks_without_a_coverage_question_behind_it(self) -> None:
        history = [ChatMessage(role="user", content="phí sản phẩm là bao nhiêu?")]
        assert not is_coverage_thread("nhưng tôi bị tai nạn thì sao", history)

    def test_the_opening_question_still_matches_on_its_own(self) -> None:
        assert is_coverage_thread("tôi bị tai nạn có được chi trả không?", [])


def test_coverage_turns_drop_the_general_knowledge_supplement() -> None:
    """It contradicted itself on exactly this question shape (2026-07-27).

    Suppression is unconditional — an explicit ``general_knowledge=True`` must
    not reopen it, so the assertion passes the flag that would normally win.
    """
    assert GENERAL_KNOWLEDGE_HEADING in system_prompt(general_knowledge=True)
    assert GENERAL_KNOWLEDGE_HEADING not in system_prompt(
        coverage=True, general_knowledge=True
    )
    assert GENERAL_KNOWLEDGE_HEADING not in system_prompt(
        coverage_undetermined=True, general_knowledge=True
    )


def test_coverage_turns_are_never_told_to_be_brief() -> None:
    """ "ngắn gọn" is the last thing the model reads and it collapsed the answer."""
    assert "ngắn gọn" in system_prompt(general_knowledge=False)
    shaped = system_prompt(coverage=True, general_knowledge=False)
    assert "ngắn gọn" not in shaped
    assert "KHÔNG rút gọn thành một câu kết luận" in shaped
    # A literal skeleton: small models copy layouts far better than they follow
    # descriptions of one.
    assert "**Trường hợp 1 — Nếu sự kiện dẫn đến TỬ VONG:**" in shaped
    assert "**Cần kiểm tra thêm để kết luận:**" in shaped


def test_prompt_requires_readable_markdown_layout() -> None:
    prompt = system_prompt(general_knowledge=False)
    assert "TRỢ LÝ TÀI LIỆU CHUYÊN NGHIỆP" in prompt
    assert "Luôn sử dụng Markdown" in prompt
    assert 'Dùng "##" cho tiêu đề của phần chính' in prompt
    assert '"###" cho tiêu đề của phần phụ' in prompt
    assert "một dòng trống sau mỗi tiêu đề" in prompt
    assert "không được có quá 3 câu" in prompt
    assert 'bắt đầu bằng "- "' in prompt
    assert "Không tạo các khối văn bản lớn" in prompt


def test_prompt_carries_the_worked_example_for_grouped_exclusions() -> None:
    """Racing ≠ a traffic accident — the misapplication seen in turns 1 and 2."""
    for advisory in (False, True):
        prompt = system_prompt(advisory=advisory, general_knowledge=False)
        assert "TAI NẠN GIAO THÔNG" in prompt
        assert 'KHÔNG phải là "đua xe"' in prompt


def test_coverage_blocks_never_weaken_the_mandatory_properties() -> None:
    # The blocks are additive: every non-negotiable rule survives (CLAUDE.md).
    for kwargs in ({"coverage": True}, {"coverage_undetermined": True}):
        prompt = system_prompt(general_knowledge=False, **kwargs)
        assert "Tôi không tìm thấy thông tin trong tài liệu" in prompt
        assert "trích dẫn nguồn bằng SỐ của đoạn ngữ cảnh" in prompt
        assert (
            "Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức" in prompt
        )
        assert "CHỈ VÌ ngữ cảnh có mục loại trừ" in prompt
