"""Tests for the pre-retrieval typo-confirmation gate (app/retrieval/spellcheck.py).

No Qdrant/Ollama needed: document titles are injected directly and the
glossary loader reads the real (committed) data/glossary/thuat_ngu.yaml.
"""

from __future__ import annotations

from app.retrieval.spellcheck import (
    build_confirmation_message,
    find_suggestions,
    is_affirmation,
    is_confirmation_prompt,
    maybe_suggest_correction,
    Suggestion,
)

_TITLES = ["SẢN PHẨM BẢO HIỂM LIÊN KẾT CHUNG"]


def test_flags_letter_level_typo_against_document_title() -> None:
    query = "cách hoạt động của các loại phí trong sản phẩm bao hiem lieen keet chung"
    suggestions = find_suggestions(query, titles=_TITLES)
    assert suggestions
    assert suggestions[0].canonical == "SẢN PHẨM BẢO HIỂM LIÊN KẾT CHUNG"


def test_does_not_flag_correct_spelling_without_diacritics() -> None:
    # Habitual no-diacritics typing must not be treated as a typo.
    query = "phi cua san pham bao hiem lien ket chung la gi"
    assert find_suggestions(query, titles=_TITLES) == []


def test_does_not_flag_unrelated_query() -> None:
    query = "giờ làm việc của văn phòng là mấy giờ"
    assert find_suggestions(query, titles=_TITLES) == []


def test_maybe_suggest_correction_builds_vietnamese_confirmation() -> None:
    query = "sản phẩm bao hiem lieen keet chung có những phí gì"
    message = maybe_suggest_correction(query, titles=_TITLES)
    assert message is not None
    assert "SẢN PHẨM BẢO HIỂM LIÊN KẾT CHUNG" in message
    assert message.endswith("để tôi tra cứu đúng tài liệu.")


def test_maybe_suggest_correction_disabled_returns_none() -> None:
    from app.config import settings as settings_module

    original = settings_module.settings.spellcheck_enabled
    settings_module.settings.spellcheck_enabled = False
    try:
        query = "sản phẩm bao hiem lieen keet chung có những phí gì"
        assert maybe_suggest_correction(query, titles=_TITLES) is None
    finally:
        settings_module.settings.spellcheck_enabled = original


def test_short_query_never_flagged() -> None:
    assert find_suggestions("chung", titles=_TITLES) == []


def test_flags_typo_of_two_word_glossary_term() -> None:
    # "phí thuần" is a distinctive 2-word glossary term; a heavily garbled
    # query must still be caught (previously skipped as too short to check).
    query = "coong thưc tinhh phis thuanf laf gi"
    suggestions = find_suggestions(query, titles=_TITLES)
    assert suggestions
    assert suggestions[0].canonical == "phí thuần"


def test_does_not_flag_chart_request_on_generic_tail() -> None:
    # A chart request whose fragment "hạn theo" coincidentally resembled the
    # generic "... nhân thọ" tail of "niên kim nhân thọ" must not be flagged:
    # the identifying words ("niên kim") are absent, so it is not that term.
    for query in (
        "vẽ cho tôi biểu đồ %Phí chấm dứt hợp đồng trước hạn theo tuổi HĐ",
        "vẽ cho tôi biểu đồ phần trăm phí chấm dứt hợp đồng trước hạn theo tuổi HĐ",
    ):
        assert find_suggestions(query, titles=_TITLES) == []


def test_does_not_flag_correct_common_word_resembling_rare_term() -> None:
    # "phí trong" (correctly-spelled: fees "in" the contract) only resembles the
    # rare term "phí ròng" by coincidence — a span of common words is not a typo.
    query = "các loại phí trong hợp đồng gồm những gì"
    assert find_suggestions(query, titles=_TITLES) == []


def test_confirmation_prompt_is_recognized_round_trip() -> None:
    # A user confirming our clarification must be routable back to their
    # question: the message we emit is recognized, an unrelated one is not.
    prompt = build_confirmation_message(
        [
            Suggestion(
                canonical="SẢN PHẨM BẢO HIỂM LIÊN KẾT CHUNG",
                matched_span="x",
                ratio=0.9,
            )
        ]
    )
    assert is_confirmation_prompt(prompt)
    assert not is_confirmation_prompt("Tôi không tìm thấy thông tin trong tài liệu.")


def test_affirmation_matches_bare_yes_only() -> None:
    for yes in ("đúng", "Đúng", "đúng rồi", "phải", "chính xác", "vâng", "OK"):
        assert is_affirmation(yes)
    # A real question that merely contains a "yes"-ish word is not a confirmation.
    for no in ("đúng vậy thì phí là bao nhiêu", "không", "sản phẩm nào"):
        assert not is_affirmation(no)


def test_does_not_flag_correctly_spelled_partial_title_match() -> None:
    # Every word is correctly spelled; the query just names a long document by a
    # shorter correct phrase. Leaked context words ("chi tiết các quyền lợi của")
    # drag the window ratio into the band, but there is no misspelled token, so
    # the query must go straight to retrieval — not trigger a confirmation prompt.
    title = (
        "Quy tắc, Điều khoản Sản phẩm Bảo hiểm tử vong và thương tật "
        "nghiêm trọng do tai nạn"
    )
    query = (
        "Liệt kê chi tiết các quyền lợi của Sản phẩm Bảo hiểm tử vong và "
        "thương tật nghiêm trọng do tai nạn"
    )
    assert find_suggestions(query, titles=[title]) == []


def test_still_flags_when_partial_title_match_has_a_real_typo() -> None:
    # Same partial match, but "thươg" is a genuine slip for "thương": a span
    # token that is not a real word yet closely resembles a phrase token — this
    # must still be flagged.
    title = (
        "Quy tắc, Điều khoản Sản phẩm Bảo hiểm tử vong và thương tật "
        "nghiêm trọng do tai nạn"
    )
    query = (
        "Liệt kê chi tiết các quyền lợi của Sản phẩm Bảo hiểm tử vong và "
        "thươg tật nghiêm trọng do tai nạn"
    )
    suggestions = find_suggestions(query, titles=[title])
    assert suggestions
    assert suggestions[0].canonical == title


def test_does_not_flag_correct_words_resembling_dropped_generic_residue() -> None:
    # A valid reserve-formula question must not be flagged: dropping the generic
    # "phí" from 3-word terms leaves 2-word residues ("toàn phần", "thực thu")
    # that coincidentally resemble correctly-spelled prose ("thành phần" from
    # "từng thành phần"; "thức tính" from "công thức tính"). Word-dropping is for
    # long titles, not short glossary terms — short terms match at full length.
    query = (
        "Trình bày công thức tính dự phòng toán học và giải thích ý nghĩa từng "
        "thành phần trong công thức. Trích dẫn tài liệu nguồn."
    )
    assert find_suggestions(query, titles=[]) == []
