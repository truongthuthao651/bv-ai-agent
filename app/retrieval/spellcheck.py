"""Pre-retrieval typo detection against known Vietnamese vocabulary.

No LLM call (mirrors query_expansion.py) — pure difflib against glossary
terms/synonyms and the titles of currently indexed documents. Vietnamese
queries typed without diacritics, or with a doubled/dropped letter (a common
mobile-keyboard slip — e.g. "lieen keet" for "liên kết"), still retrieve
reasonably well via bge-m3's semantic embeddings, but silently guessing which
document the user meant risks answering about the wrong product. Instead this
stage asks the user to confirm the intended term before retrieval runs at all.

Diacritics are folded away before comparison so habitual no-diacritics typing
(extremely common in Vietnamese) is never mistaken for a typo — only genuine
letter-level slips lower the match ratio enough to trigger a suggestion.

To stay precise on short terms without going blind to them, a match must cover
most of a phrase's *distinctive* tokens (the words that identify it, as opposed
to generic domain words like "phí"/"bảo hiểm" or a "... nhân thọ" tail shared
across many products). This lets a full two-word term like "phí thuần" be
checked while a coincidental resemblance to a generic fragment is rejected.
"""

from __future__ import annotations

import logging
import math
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.config.settings import settings
from app.retrieval.query_expansion import load_glossary

logger = logging.getLogger(__name__)

_DIACRITIC_MAP = str.maketrans({"đ": "d", "Đ": "D"})

# How many leading/trailing words of a known phrase a user may plausibly drop
# (e.g. "sản phẩm bảo hiểm liên kết chung" -> "bảo hiểm liên kết chung").
_MAX_DROPPED_WORDS = 2

# A reduced (dropped-word) window must retain at least this many words. Word
# dropping is meant for long document titles shedding a generic prefix; a short
# glossary term reduced to a 2-word residue ("phí toàn phần" -> "toàn phần")
# carries too little identity and collides with ordinary correctly-spelled prose
# ("thành phần"), so short phrases are only ever matched at their full length.
_MIN_REDUCED_WINDOW = 3

# A phrase token appearing in at least this many distinct known phrases is a
# generic domain word (e.g. "phí", "bảo", "hiểm") — derived from the corpus so
# no hand-maintained domain list is needed.
_GENERIC_DF = 3

# Generic words a corpus-frequency check can't catch because they happen to be
# rare in the glossary itself: Vietnamese function words and generic product
# modifiers ("sản phẩm" = product). Folded (diacritics/case removed) to match
# _normalize. These, together with any token whose document frequency reaches
# _GENERIC_DF, are the words a partial-phrase match may leave uncovered.
_FUNCTION_WORDS = frozenset(
    {
        "la",
        "gi",
        "cua",
        "va",
        "cac",
        "mot",
        "trong",
        "theo",
        "cho",
        "toi",
        "voi",
        "co",
        "nhung",
        "nay",
        "do",
        "khi",
        "de",
        "o",
        "ve",
        "nhu",
        "duoc",
        "can",
        "phai",
        "nguoi",
        "nao",
        "ra",
        "san",
        "pham",
        "so",
        "loai",
    }
)


def _normalize(text: str) -> str:
    """Fold Vietnamese diacritics and case away for fuzzy comparison."""
    decomposed = unicodedata.normalize("NFD", text.translate(_DIACRITIC_MAP))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower().strip()


@dataclass
class Suggestion:
    """One known phrase the query likely garbled."""

    canonical: str  # correctly-spelled phrase to show the user
    matched_span: str  # the query fragment it appears to correspond to
    ratio: float


def _known_phrases(titles: list[str] | None) -> list[str]:
    """Glossary terms/synonyms plus indexed document titles, deduped."""
    phrases = []
    for entry in load_glossary():
        phrases.extend(entry.names)
    if titles is None:
        try:
            from app.ingestion import indexer  # lazy: keeps this module import-light

            titles = [d.doc_title for d in indexer.list_documents()]
        except Exception:  # pragma: no cover - Qdrant unavailable/offline
            logger.warning(
                "Could not load document titles for spellcheck", exc_info=True
            )
            titles = []
    phrases.extend(titles)
    return sorted({p.strip() for p in phrases if p.strip()}, key=len, reverse=True)


def _generic_tokens(phrases: list[str]) -> frozenset[str]:
    """Folded tokens that must never, on their own, anchor a typo match.

    A token is generic if it occurs across many known phrases (document
    frequency >= ``_GENERIC_DF`` — e.g. "phí", "bảo", "hiểm") or is a known
    function word / product modifier. Everything else is *distinctive*: the
    part of a phrase that actually identifies which term the user meant.
    """
    df: dict[str, int] = {}
    for phrase in phrases:
        for tok in set(_normalize(phrase).split()):
            df[tok] = df.get(tok, 0) + 1
    return frozenset({t for t, c in df.items() if c >= _GENERIC_DF} | _FUNCTION_WORDS)


def _covers_distinctive(
    phrase_words: list[str], window_words: list[str], generic: frozenset[str]
) -> bool:
    """True if this prefix/suffix window keeps most of the phrase's identity.

    A word-dropping match is only trustworthy when the retained window still
    contains at least half of the phrase's *distinctive* (non-generic) tokens.
    This separates a real dropped-modifier match ("sản phẩm bảo hiểm liên kết
    chung" -> "bảo hiểm liên kết chung", keeping "liên kết chung") from a
    coincidental one where a query fragment resembles a generic tail like
    "nhân thọ" while the distinctive "niên kim" is dropped.
    """
    distinctive = {
        t for t in _normalize(" ".join(phrase_words)).split() if t not in generic
    }
    if not distinctive:
        return False  # an all-generic phrase (e.g. "bảo hiểm") anchors nothing
    retained = {
        t for t in _normalize(" ".join(window_words)).split() if t not in generic
    }
    return len(retained & distinctive) >= math.ceil(len(distinctive) / 2)


def _window_ratio(
    query_words: list[str],
    phrase_words: list[str],
    *,
    stop_ratio: float,
    generic: frozenset[str],
) -> tuple[float, str]:
    """Best match ratio between a query word-window and a prefix/suffix of ``phrase_words``.

    Tries the full phrase length first, then progressively shorter
    prefixes/suffixes (tolerating dropped leading words like "sản phẩm ...").
    A prefix/suffix is only considered if it still covers most of the phrase's
    distinctive tokens (``_covers_distinctive``) — this is what stops a generic
    tail ("nhân thọ") from matching while the identifying words are dropped.
    Stops at the *first* (largest) surviving window size that reaches
    ``stop_ratio`` and returns that window's own ratio.
    """
    n = len(phrase_words)
    min_w = max(2, n - _MAX_DROPPED_WORDS)
    for w in range(n, min_w - 1, -1):
        if len(query_words) < w:
            continue
        # Only match at full phrase length, or on a window still long enough to
        # be identifying: never shrink a phrase down to a 2-word residue (see
        # _MIN_REDUCED_WINDOW). This stops a dropped-generic tail like "toàn
        # phần" from matching correctly-spelled prose ("thành phần").
        if w < n and w < _MIN_REDUCED_WINDOW:
            continue
        candidates = {
            " ".join(cw)
            for cw in (phrase_words[:w], phrase_words[-w:])
            if _covers_distinctive(phrase_words, cw, generic)
        }
        if not candidates:
            continue
        best_ratio, best_span = 0.0, ""
        for i in range(len(query_words) - w + 1):
            window = query_words[i : i + w]
            # A garbled term yields tokens that are neither generic domain words
            # nor function words; a span made entirely of correctly-spelled
            # common words (e.g. "phí trong") only *resembles* a rare term like
            # "phí ròng" by coincidence and must not be flagged as a typo.
            if all(_normalize(word) in generic for word in window):
                continue
            window_norm = _normalize(" ".join(window))
            for cand in candidates:
                ratio = SequenceMatcher(None, window_norm, _normalize(cand)).ratio()
                if ratio > best_ratio:
                    best_ratio, best_span = ratio, " ".join(window)
        if best_ratio >= stop_ratio:
            return best_ratio, best_span
    return 0.0, ""


def _vocabulary(phrases: list[str]) -> frozenset[str]:
    """Every folded token that appears in some known phrase — the set of real words.

    A query token found here is spelled correctly (it is a word the corpus
    actually uses), so it can never be a typo — even when it happens to resemble
    a *different* phrase's token ("nghiêm" contains "hiểm"; "trọng" is one letter
    from "trọn"). This is what separates such near-homographs from real slips.
    """
    vocab: set[str] = set()
    for phrase in phrases:
        vocab.update(_normalize(phrase).split())
    return frozenset(vocab)


def _span_has_typo(
    span: str,
    phrase: str,
    generic: frozenset[str],
    vocab: frozenset[str],
    typo_ratio: float,
) -> bool:
    """True if ``span`` contains a genuinely *misspelled* word relative to ``phrase``.

    A high window ratio alone isn't a typo: a correctly-spelled *partial* title
    match ("...quyền lợi của Sản phẩm Bảo hiểm tử vong...") lands in the ratio
    band merely because leaked/omitted context words drag the score down, while
    every word the user typed is a real word. A typo, by contrast, leaves a span
    token that is *not a known word* (absent from ``vocab``) yet closely resembles
    one of the phrase's own tokens ("lieen"~"liên"). We flag only the latter.
    Generic words, exact phrase tokens, and any token the corpus actually uses are
    all correctly spelled and never qualify.
    """
    phrase_tokens = set(_normalize(phrase).split())
    for tok in _normalize(span).split():
        if tok in generic or tok in vocab:
            continue  # generic word, or a real word the corpus uses — not a slip
        if any(
            SequenceMatcher(None, tok, pt).ratio() >= typo_ratio for pt in phrase_tokens
        ):
            return True
    return False


def find_suggestions(
    query: str,
    *,
    titles: list[str] | None = None,
    min_ratio: float | None = None,
    max_ratio: float | None = None,
    typo_ratio: float | None = None,
) -> list[Suggestion]:
    """Find known phrases the query likely garbled (close, but not exact/correct).

    A ratio near 1.0 means the query already spells the phrase correctly
    (diacritics aside) — not flagged. A ratio below ``min_ratio`` isn't
    similar enough to be worth interrupting the user about. Only the band in
    between is a *candidate*; it is flagged only if the matched span actually
    contains a misspelled word (``_span_has_typo``), so a correctly-spelled
    partial title match proceeds straight to retrieval instead of prompting.
    """
    min_ratio = settings.spellcheck_min_ratio if min_ratio is None else min_ratio
    max_ratio = settings.spellcheck_max_ratio if max_ratio is None else max_ratio
    typo_ratio = (
        settings.spellcheck_typo_token_ratio if typo_ratio is None else typo_ratio
    )
    query_words = query.split()
    if len(query_words) < 2:
        return []

    phrases = _known_phrases(titles)
    generic = _generic_tokens(phrases)
    vocab = _vocabulary(phrases)
    seen: set[str] = set()
    suggestions: list[Suggestion] = []
    for phrase in phrases:
        phrase_words = phrase.split()
        if len(phrase_words) < 2:
            continue  # single-word terms have no distinctive multi-word anchor
        ratio, span = _window_ratio(
            query_words, phrase_words, stop_ratio=min_ratio, generic=generic
        )
        key = phrase.lower()
        if (
            min_ratio <= ratio < max_ratio
            and key not in seen
            and _span_has_typo(span, phrase, generic, vocab, typo_ratio)
        ):
            seen.add(key)
            suggestions.append(
                Suggestion(canonical=phrase, matched_span=span, ratio=ratio)
            )

    suggestions.sort(key=lambda s: s.ratio, reverse=True)
    return suggestions[:3]


# Tail shared verbatim by both clarification messages below. Used to recognize
# our own prior clarification turn when the user replies to it (the gate is
# otherwise stateless — see is_confirmation_prompt).
_CONFIRMATION_SIGNATURE = "để tôi tra cứu đúng tài liệu"

# Bare "yes, that's right" replies a user might send to accept a suggested term,
# folded (diacritics/case removed) to match _normalize. Matched only against the
# whole message, so these never swallow a real question that merely contains one.
_AFFIRMATIONS = frozenset(
    {
        "dung",
        "dung roi",
        "dung vay",
        "dung roi do",
        "phai",
        "phai roi",
        "chinh xac",
        "vang",
        "u",
        "ung",
        "ok",
        "oke",
        "okay",
        "yes",
    }
)


def build_confirmation_message(suggestions: list[Suggestion]) -> str:
    """The Vietnamese clarification message asking the user to confirm terms."""
    if len(suggestions) == 1:
        term = suggestions[0].canonical
        return (
            f'Ý bạn có phải là "{term}" không? Vui lòng xác nhận hoặc nhập lại '
            "câu hỏi với từ ngữ chính xác để tôi tra cứu đúng tài liệu."
        )
    options = "; ".join(f'"{s.canonical}"' for s in suggestions)
    return (
        f"Câu hỏi có thể chứa từ ngữ chưa chính xác. Ý bạn có phải là một trong "
        f"các mục sau: {options}? Vui lòng xác nhận hoặc nhập lại câu hỏi với từ "
        "ngữ chính xác để tôi tra cứu đúng tài liệu."
    )


def is_confirmation_prompt(text: str) -> bool:
    """True if ``text`` is one of our own spellcheck clarification messages.

    Lets the stateless chat endpoint recognize that the previous assistant turn
    asked the user to confirm a term, so a bare "đúng" reply can be routed back
    to the original question instead of being retrieved on literally.
    """
    return _CONFIRMATION_SIGNATURE in text


def is_affirmation(text: str) -> bool:
    """True if the whole message is a bare confirmation ("đúng", "phải", ...)."""
    return _normalize(text) in _AFFIRMATIONS


def maybe_suggest_correction(
    query: str, *, titles: list[str] | None = None
) -> str | None:
    """Deterministic pre-retrieval gate: ask before answering on a likely typo.

    Returns a Vietnamese clarification message when the query likely garbles a
    known glossary term or document title, or None to proceed with retrieval
    unchanged. Disabled entirely via ``settings.spellcheck_enabled``.
    """
    if not settings.spellcheck_enabled:
        return None
    suggestions = find_suggestions(query, titles=titles)
    if not suggestions:
        return None
    return build_confirmation_message(suggestions)
