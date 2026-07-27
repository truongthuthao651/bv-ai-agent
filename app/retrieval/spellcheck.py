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

"Is this a real word?" is answered by the vocabulary of the INDEXED CORPUS, not
just the glossary and document titles (see ``_vocabulary``): a few hundred
phrase words leave ordinary Vietnamese looking unknown, and a short unknown
token resembles some phrase token by accident.

To stay precise on short terms without going blind to them, a match must cover
most of a phrase's *distinctive* tokens (the words that identify it, as opposed
to generic domain words like "phí"/"bảo hiểm" or a "... nhân thọ" tail shared
across many products). This lets a full two-word term like "phí thuần" be
checked while a coincidental resemblance to a generic fragment is rejected.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.config.settings import settings
from app.retrieval.query_expansion import load_glossary

logger = logging.getLogger(__name__)

_DIACRITIC_MAP = str.maketrans({"đ": "d", "Đ": "D"})

# Fold punctuation away too: whitespace-splitting alone leaves trailing marks
# glued to words ("bền." -> token "ben."), and a correctly-spelled word with a
# clinging period/comma is then absent from the known vocabulary and mistaken
# for a misspelling of the same word without it (see _span_has_typo). Replace
# any non-word/non-space char with a space so tokens are punctuation-free.
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")

# A reduced (dropped-word) window must retain at least this many words. Word
# dropping is meant for long document titles shedding a generic prefix/suffix
# (e.g. "SẢN PHẨM BẢO HIỂM HỖN HỢP Lộc Vững Bền" -> "Lộc Vững Bền"); a short
# glossary term reduced to a 2-word residue ("phí toàn phần" -> "toàn phần")
# carries too little identity and collides with ordinary correctly-spelled prose
# ("thành phần"), so short phrases are only ever matched at their full length.
# How far a title may shrink is gated by ``_covers_distinctive``, not a fixed
# drop count — real ingested titles often carry 4–6 generic leading words.
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
    """Fold Vietnamese diacritics, case, and punctuation away for fuzzy comparison."""
    decomposed = unicodedata.normalize("NFD", text.translate(_DIACRITIC_MAP))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    depunctuated = _PUNCT_RE.sub(" ", stripped.lower())
    return _WHITESPACE_RE.sub(" ", depunctuated).strip()


@dataclass
class Suggestion:
    """One known phrase the query likely garbled."""

    canonical: str  # correctly-spelled phrase to show the user
    matched_span: str  # the query fragment it appears to correspond to
    ratio: float


def _indexed_corpus() -> tuple[list[str], frozenset[str]]:
    """``(document titles, every folded word the corpus uses)`` from the index.

    Both come from one cached scroll (``indexer.corpus_snapshot``), rebuilt only
    after an ingest. Empty when Qdrant is unavailable, which degrades the gate
    to titles+glossary rather than failing the query.
    """
    try:
        from app.ingestion import indexer  # lazy: keeps this module import-light

        titles, texts = indexer.corpus_snapshot(indexer.index_version())
    except Exception:  # pragma: no cover - Qdrant unavailable/offline
        logger.warning(
            "Could not load the indexed corpus for spellcheck", exc_info=True
        )
        return [], frozenset()
    words: set[str] = set()
    for text in texts:
        words.update(_normalize(text).split())
    return list(titles), frozenset(words)


def _known_phrases(titles: list[str]) -> list[str]:
    """Glossary terms/synonyms plus indexed document titles, deduped."""
    phrases = []
    for entry in load_glossary():
        phrases.extend(entry.names)
    phrases.extend(titles)
    return sorted({p.strip() for p in phrases if p.strip()}, key=len, reverse=True)


def _is_token_subsequence(short: list[str], long: list[str]) -> bool:
    """True if ``short`` appears as a contiguous run inside ``long``."""
    if not short or len(short) > len(long):
        return False
    n = len(short)
    return any(long[i : i + n] == short for i in range(len(long) - n + 1))


def _phrases_for_df(phrases: list[str]) -> list[str]:
    """Folded phrases with nested title variants removed (keep the longest).

    Ingested docs often yield both a short product name and a longer title that
    contains it ("An Lộc Vững Bền" ⊂ "Bảo hiểm … An Lộc Vững Bền"). Counting
    both would inflate document frequency of the product-name tokens and mark
    them generic, blinding the typo gate to that product.
    """
    norms = sorted(
        {_normalize(p) for p in phrases if p.strip()},
        key=len,
        reverse=True,
    )
    kept: list[str] = []
    for norm in norms:
        tokens = norm.split()
        if any(_is_token_subsequence(tokens, k.split()) for k in kept):
            continue
        kept.append(norm)
    return kept


def _generic_tokens(phrases: list[str]) -> frozenset[str]:
    """Folded tokens that must never, on their own, anchor a typo match.

    A token is generic if it occurs across many known phrases (document
    frequency >= ``_GENERIC_DF`` — e.g. "phí", "bảo", "hiểm") or is a known
    function word / product modifier. Everything else is *distinctive*: the
    part of a phrase that actually identifies which term the user meant.
    Nested title variants are deduped before the DF pass so a product name
    repeated inside longer titles is not mistaken for a generic domain word.
    """
    df: dict[str, int] = {}
    for phrase in _phrases_for_df(phrases):
        for tok in set(phrase.split()):
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
    prefixes/suffixes (tolerating dropped generic title words like
    "sản phẩm bảo hiểm hỗn hợp ..."). Shrinks as far as
    ``_MIN_REDUCED_WINDOW``; a prefix/suffix is only considered if it still
    covers most of the phrase's distinctive tokens (``_covers_distinctive``) —
    this is what stops a generic tail ("nhân thọ") from matching while the
    identifying words are dropped.

    Returns the *highest*-ratio surviving window (not the longest). Long
    ingested titles otherwise let a mediocre mid-length prefix/suffix clear
    ``stop_ratio`` and shadow a near-exact product-name suffix — which would
    both miss real Telex slips and false-flag habitual no-diacritics typing.
    """
    n = len(phrase_words)
    min_w = _MIN_REDUCED_WINDOW if n >= _MIN_REDUCED_WINDOW else 2
    best_ratio, best_span = 0.0, ""
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
                # Prefer higher ratio; on a tie keep the longer span (encountered
                # first because ``w`` descends).
                if ratio > best_ratio:
                    best_ratio, best_span = ratio, " ".join(window)
    if best_ratio >= stop_ratio:
        return best_ratio, best_span
    return 0.0, ""


def _vocabulary(phrases: list[str], corpus_words: frozenset[str]) -> frozenset[str]:
    """Every folded token the corpus actually uses — the set of real words.

    A query token found here is spelled correctly, so it can never be a typo —
    even when it happens to resemble a *different* phrase's token ("nghiêm"
    contains "hiểm"; "trọng" is one letter from "trọn"). This is what separates
    such near-homographs from real slips.

    It must cover known phrases AND the body text of indexed documents. Built
    from phrases alone it is only a few hundred words, so ordinary Vietnamese
    ("giữa", "hồ") counts as unknown, and short unknown tokens resemble
    something by accident — ``giua``/``gia`` scores 0.857 and ``ho``/``hợp``
    0.800, which flagged "Mối liên hệ giữa..." and "Hồ sơ..." as typos. Real
    slips ("lieen", "vuwng") appear in no document, so widening the vocabulary
    removes those false positives without blunting detection.
    """
    vocab: set[str] = set(corpus_words)
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
    corpus_words: frozenset[str] | None = None,
    min_ratio: float | None = None,
    max_ratio: float | None = None,
    typo_ratio: float | None = None,
) -> list[Suggestion]:
    """Find known phrases the query likely garbled (close, but not exact/correct).

    A ratio below ``min_ratio`` isn't similar enough to be worth interrupting
    the user about. Above that floor, a candidate is flagged only if the
    matched span actually contains a misspelled word (``_span_has_typo``):
    habitual no-diacritics typing folds to an exact known-vocab match and is
    never flagged, while a real slip (``thươg``~``thương``, ``vuwng``~``vững``)
    is — even when the rest of a long title keeps the window ratio near 1.0.

    ``max_ratio`` is accepted for call-site compatibility but no longer gates
    suggestions; the typo-token check is the authoritative "already correct"
    filter.

    Passing ``titles`` explicitly keeps this hermetic (no Qdrant): the indexed
    corpus is then only consulted for ``corpus_words`` if that is also omitted.
    """
    min_ratio = settings.spellcheck_min_ratio if min_ratio is None else min_ratio
    # Signature / .env compat only — the typo-token check replaced this upper gate.
    _max_ratio = settings.spellcheck_max_ratio if max_ratio is None else max_ratio
    typo_ratio = (
        settings.spellcheck_typo_token_ratio if typo_ratio is None else typo_ratio
    )
    query_words = query.split()
    if len(query_words) < 2:
        return []

    if titles is None:
        indexed_titles, indexed_words = _indexed_corpus()
        titles = indexed_titles
        if corpus_words is None:
            corpus_words = indexed_words
    phrases = _known_phrases(titles)
    generic = _generic_tokens(phrases)
    vocab = _vocabulary(phrases, corpus_words or frozenset())
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
            ratio >= min_ratio
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


def apply_suggestions(query: str, suggestions: list[Suggestion]) -> str:
    """Rewrite ``query`` by substituting each matched span with its canonical form.

    Used when the user confirms a spellcheck prompt: replaying the *raw* typo
    query would re-run retrieval on the same garbled text (and often miss
    product cues needed for comparison routing). Longest span first so a
    longer title match isn't partially overwritten by a shorter nested one.
    """
    if not suggestions or not query:
        return query
    out = query
    for suggestion in sorted(
        suggestions, key=lambda s: len(s.matched_span), reverse=True
    ):
        span = suggestion.matched_span
        if not span:
            continue
        if span in out:
            out = out.replace(span, suggestion.canonical, 1)
            continue
        # Case-insensitive fallback (user may have mixed casing).
        lower = out.lower()
        idx = lower.find(span.lower())
        if idx >= 0:
            out = out[:idx] + suggestion.canonical + out[idx + len(span) :]
    return out


def corrected_query_after_confirmation(original_query: str) -> str:
    """Re-detect suggestions on ``original_query`` and apply them.

    The chat endpoint is stateless across the confirm turn, so we recompute the
    same suggestions that produced the clarification rather than parsing the
    assistant message. No-op when nothing matches (or spellcheck is off).
    """
    if not settings.spellcheck_enabled:
        return original_query
    suggestions = find_suggestions(original_query)
    if not suggestions:
        return original_query
    return apply_suggestions(original_query, suggestions)


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
