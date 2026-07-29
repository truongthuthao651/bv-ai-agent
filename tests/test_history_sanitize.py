"""Replayed assistant turns must not carry the suffixes we appended to them.

Encodes the compounding failure observed on a real policy PDF (2026-07-27):
Open WebUI returns the rendered answer, we replayed it verbatim, the model
imitated the "Nguồn tham khảo" block it saw under its own numbering, and
``_sources_suffix`` appended a canonical block beneath it — three source blocks
in one answer by the fourth turn, with conflicting numbers.
"""

from __future__ import annotations

from app.generation.generator import SourcesTruncator, build_messages
from app.generation.history import (
    strip_appended_artifacts,
    truncate_at_sources_heading,
)
from app.generation.prompts import (
    CALC_DISCLAIMER,
    GENERAL_KNOWLEDGE_DISCLAIMER,
    SOURCES_HEADING,
)
from app.models.schemas import ChatMessage

# One rendered assistant turn as Open WebUI hands it back: answer, the label
# the generator appended, the sources block, then the response-time footer.
_RENDERED = f"""\
Quyền lợi tử vong được chi trả theo [1].

{GENERAL_KNOWLEDGE_DISCLAIMER}

{SOURCES_HEADING}
- [1] Quy tắc sản phẩm — QUYỀN LỢI TỬ VONG (trang 4)

_⏱ Thời gian trả lời: 1m16s_"""


def test_strips_every_appended_artifact_but_keeps_the_answer() -> None:
    cleaned = strip_appended_artifacts(_RENDERED)
    assert cleaned == "Quyền lợi tử vong được chi trả theo [1]."
    assert SOURCES_HEADING not in cleaned
    assert "⏱" not in cleaned
    assert GENERAL_KNOWLEDGE_DISCLAIMER not in cleaned


def test_strips_a_model_written_block_and_our_own_block_together() -> None:
    """Turn 4 of the reported conversation: the model wrote its own block first.

    Cutting at the FIRST heading has to take both, otherwise the model's
    conflicting numbering survives into the next turn's context.
    """
    doubled = (
        "Không được claim.\n\n"
        f"{SOURCES_HEADING}\n- [1] Quy tắc sản phẩm — LOẠI TRỪ (trang 8)\n\n"
        f"{GENERAL_KNOWLEDGE_DISCLAIMER}\n\n"
        f"{SOURCES_HEADING}\n- [3] Quy tắc sản phẩm — LOẠI TRỪ (trang 8)\n"
    )
    assert strip_appended_artifacts(doubled) == "Không được claim."


def test_keeps_a_turn_that_has_no_artifacts_unchanged() -> None:
    plain = "Tôi không tìm thấy thông tin trong tài liệu."
    assert strip_appended_artifacts(plain) == plain


def test_calc_disclaimer_is_dropped_even_without_a_sources_block() -> None:
    answer = f"Phí là $P = 100$.\n\n{CALC_DISCLAIMER}"
    assert strip_appended_artifacts(answer) == "Phí là $P = 100$."


def test_build_messages_replays_the_cleaned_turn_and_drops_empty_ones() -> None:
    history = [
        ChatMessage(role="user", content="Tử vong có được chi trả không?"),
        ChatMessage(role="assistant", content=_RENDERED),
        # An assistant turn that was nothing but artifacts contributes nothing.
        ChatMessage(role="assistant", content=f"{SOURCES_HEADING}\n- [1] X — Y"),
    ]
    messages = build_messages("Còn thương tật thì sao?", [], history)
    replayed = [m for m in messages if m["role"] == "assistant"]
    assert len(replayed) == 1
    assert replayed[0]["content"] == "Quyền lợi tử vong được chi trả theo [1]."
    # The user's own turns are never touched.
    assert messages[1]["content"] == "Tử vong có được chi trả không?"


def test_truncates_at_a_sources_heading_in_a_fresh_answer() -> None:
    answer = f"Được chi trả theo [1].\n\n{SOURCES_HEADING}\n- [1] sai số"
    assert truncate_at_sources_heading(answer) == "Được chi trả theo [1]."


class TestSourcesTruncator:
    """The streaming half: a model-written block must never reach the user."""

    def test_passes_text_through_until_the_heading(self) -> None:
        t = SourcesTruncator()
        assert t.feed("Được chi trả ") == "Được chi trả "
        assert t.feed("theo [1].") == "theo [1]."

    def test_swallows_the_heading_and_everything_after_it(self) -> None:
        t = SourcesTruncator()
        out = t.feed(f"Được chi trả.\n\n{SOURCES_HEADING}\n- [1] X")
        assert out == "Được chi trả.\n\n"
        assert t.feed("\n- [2] Y") == ""
        assert t.flush() == ""

    def test_catches_a_heading_split_across_token_deltas(self) -> None:
        t = SourcesTruncator()
        emitted = "".join(
            t.feed(part) for part in ("Xong.\n\n**Nguồn ", "tham khảo:**\n- [1] X")
        )
        assert emitted == "Xong.\n\n"
        assert t.flush() == ""

    def test_flushes_a_buffered_tail_that_never_became_a_heading(self) -> None:
        t = SourcesTruncator()
        # "**Ngu" is a live prefix of the heading and gets held back...
        assert t.feed("Kết luận: **Ngu") == "Kết luận: "
        # ...then turns out to be ordinary text.
        assert t.feed("yên tắc**") + t.flush() == "**Nguyên tắc**"
