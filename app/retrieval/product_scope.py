"""Deterministic product-scope guard.

Retrieval has no product filter, so a query naming a *specific* product that is
NOT in the corpus can still return semantically-similar chunks from a DIFFERENT
product — life-insurance benefit clauses ("quyền lợi tử vong", "quyền lợi đáo
hạn", ...) are near-identical across products, so the reranker keeps them above
its floor and the model then answers, citing the wrong product. (Observed:
asking about "An Thịnh Phúc Niên", which had been deleted, produced an answer
sourced from "An Khang Như Ý".)

This module detects that case from the query text plus the titles of the
retrieved documents, so the chat endpoint can refuse deterministically instead
of answering from the wrong product — the same guardrail pattern used for the
calc/hybrid disclaimers (a small local model can't be trusted to notice the
mismatch on its own).

How it works: it isolates the product-name phrase that follows a product cue
("bảo hiểm ...", "sản phẩm ...") in the query, then checks whether any of that
phrase's distinctive tokens appears in *any* retrieved document title. If none
do, the named product is absent from what was retrieved → refuse. Matching is
diacritic-folded so habitual no-diacritics typing ("an thinh phuc nien") still
lines up with a diacritic title.

Note: a present product whose title is a bare abbreviation (e.g. "BHLKC_AKNY")
carries none of the product-name tokens, so this guard will (correctly, per the
existing doc-title/retrieval guidance) refuse until the document is re-ingested
with a "Tên tài liệu" that spells the product name out — turning a silent
wrong-product answer into a loud, actionable refusal.

Pure and offline — unit-tested without Qdrant or an LLM.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable

from app.models.schemas import DocType, Hit
from app.text_utils import fold_text as _fold

# Product cue phrases (diacritic-folded); the product name is whatever noun
# phrase follows one of these in the query.
_TRIGGERS: tuple[tuple[str, ...], ...] = (
    ("bao", "hiem"),
    ("san", "pham"),
    ("hop", "dong"),
    ("chuong", "trinh"),
    ("goi",),
)

# Generic tokens (diacritic-folded) that are NEVER part of a distinctive product
# name: insurance product-type connectors ("liên kết chung", "hỗn hợp", "nhân
# thọ"...) plus question/filler/verb words. Used both to skip leading connectors
# right after a trigger and to terminate the product-name span.
_GENERIC: frozenset[str] = frozenset(
    {
        # insurance-generic nouns / product-type connectors
        "bao",
        "hiem",
        "san",
        "pham",
        "goi",
        "chuong",
        "trinh",
        "hop",
        "dong",
        "lien",
        "ket",
        "chung",
        "hon",
        "nhan",
        "tho",
        "tu",
        "ky",
        "tron",
        "doi",
        "an",
        "loai",
        "gom",
        "bao_gom",
        # document-title boilerplate (AGENT1, 2026-08-05 audit): every indexed
        # policy title starts "Quy tắc, Điều khoản Sản phẩm ...", so without
        # these, _distinctive_title_tokens() counted them as product-distinctive
        # and inflated `needed` past what an informal mention (which never says
        # "quy tắc điều khoản") could reach — live-reproduced 3/3 near-refusal
        # on "so sánh An Vui Toàn Diện và An Bình Trọn Đời".
        "quy",
        "tac",
        "dieu",
        "khoan",
        # NEW1/q08 (2026-08-05 audit, Day 5 triage): "gia" is the folded form
        # of "gia", "giá" (price/value — "giá trị"), AND "giả" ("giả định" =
        # assumed/hypothetical) all at once (unicodedata strips the acute AND
        # hook-above accents identically); "dinh" folds "định"/"đình". Every
        # internal-guide doc in this corpus is suffixed "(tài liệu nội bộ giả
        # định)"/"(bản giả định)", so an ordinary calculation question phrased
        # "lãi suất giả định" (an assumed rate — routine actuarial phrasing,
        # q08) picked up {gia, dinh} as a false >=2-token match against an
        # UNRELATED title ("Quy trình Giải quyết... (bản giả định)"), and the
        # product-scope guard refused a fully-answerable, correctly-retrieved
        # (rank 1, score 0.999) question. Neither token is a plausible
        # standalone product-name component in this corpus (see AGENT1).
        # "dinh" is deliberately omitted: it appears in real product names
        # ("An Tâm Hoạch Định"). Lone "giả định" false matches are blocked
        # by ``overlap <= _TITLE_ONLY_CANDIDATES`` in ``mentioned_doc_titles``.
        "gia",
        # question / filler / verb words
        "la",
        "gi",
        "co",
        "cua",
        "cho",
        "ve",
        "nhu",
        "the",
        "nao",
        "nhieu",
        "liet",
        "ke",
        "chi",
        "tiet",
        "quyen",
        "loi",
        "cac",
        "va",
        "nhung",
        "mot",
        "voi",
        "duoc",
        "hay",
        "can",
        "muon",
        "xin",
        "hoi",
        "thong",
        "tin",
        "den",
        "tai",
        "theo",
        "khi",
        "cung",
        "hoac",
        "danh",
        "sach",
        "toi",
        "ban",
        "minh",
        "biet",
        "giup",
        "gium",
        "xem",
        "tra",
        "cuu",
        "nay",
        "do",
        "kia",
        "tat",
        "ca",
        "nhe",
        "a",
        "voi_lai",
    }
)

# Generics that can sit *inside* a product name between distinctive tokens
# ("An Khang Như Ý") without ending the span. "và" stays a hard terminator so
# "A và B" still yields two separate products.
_NAME_BRIDGES: frozenset[str] = frozenset({"nhu"})

# Generic tokens that may still complete a product-name span when they
# immediately follow a distinctive token ("Hoạch Định").
_NAME_SUFFIX_ALLOW: frozenset[str] = frozenset({"dinh"})

# The company's OWN name is not a product name. "sản phẩm bảo hiểm của Bảo Việt
# Life" used to yield the span ["viet", "life"], which no document title covers,
# so the guard refused a perfectly answerable question. Longest phrase first so
# "bảo việt life" is consumed whole rather than leaving a stray "life".
_COMPANY_SELF_PHRASES: tuple[tuple[str, ...], ...] = (
    ("bao", "viet", "nhan", "tho"),
    ("bao", "viet", "life"),
    ("bao", "viet"),
    ("bvl",),
)

# Tokens that end the skip-over-connectors scan after a cue phrase. Without
# them, "sản phẩm bảo hiểm của X và các công ty khác" skips right across the
# clause boundary and collects whatever noun follows as a "product name".
_HARD_SEPARATORS: frozenset[str] = frozenset({"va", "hoac", "hay"})


def _strip_company_self_reference(tokens: list[str]) -> list[str]:
    """Drop mentions of our own company so they can't be read as a product."""
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        for phrase in _COMPANY_SELF_PHRASES:
            if tuple(tokens[i : i + len(phrase)]) == phrase:
                i += len(phrase)
                break
        else:
            out.append(tokens[i])
            i += 1
    return out


def _fold_tokens(text: str) -> list[str]:
    """Diacritic-folded word tokens of ``text`` (Unicode-aware, punctuation dropped)."""
    return re.findall(r"\w+", _fold(text), flags=re.UNICODE)


def _collect_name_run(tokens: list[str], start: int) -> tuple[list[str], int]:
    """Collect distinctive name tokens from ``start``, allowing ``_NAME_BRIDGES``.

    Returns ``(span, index_after_run)``. Bridge tokens are skipped (not added to
    the distinctive span) so "khang nhu y" → ``["khang", "y"]``.
    """
    span: list[str] = []
    j = start
    n = len(tokens)
    while j < n:
        tok = tokens[j]
        if tok not in _GENERIC:
            span.append(tok)
            j += 1
            continue
        if tok in _NAME_SUFFIX_ALLOW and span:
            span.append(tok)
            j += 1
            continue
        if (
            tok in _NAME_BRIDGES
            and span
            and j + 1 < n
            and tokens[j + 1] not in _GENERIC
        ):
            j += 1  # skip bridge, keep collecting
            continue
        break
    return span, j


def _product_spans(tokens: list[str]) -> list[list[str]]:
    """All distinctive product-name spans in order of appearance (deduped).

    Scans for a trigger (``bảo hiểm`` ...), skips the generic connectors right
    after it (``liên kết chung``, ``an`` ...), then collects the name run.
    Comparison questions ("A và B") yield one span per product.

    Our own company name is removed first (it is not a product), and the
    connector skip stops at a clause boundary so a cue phrase cannot reach
    across "và" and claim an unrelated noun as a product name.
    """
    tokens = _strip_company_self_reference(tokens)
    n = len(tokens)
    spans: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    i = 0
    while i < n:
        matched = 0
        for trig in _TRIGGERS:
            if tuple(tokens[i : i + len(trig)]) == trig:
                matched = len(trig)
                break
        if not matched:
            i += 1
            continue
        j = i + matched
        while j < n and tokens[j] in _GENERIC:  # skip leading connectors
            if tokens[j] in _HARD_SEPARATORS:  # never cross a clause boundary
                break
            j += 1
        span, j = _collect_name_run(tokens, j)
        key = tuple(span)
        if span and key not in seen:
            seen.add(key)
            spans.append(span)
        i = max(j, i + 1)
    return spans


def _product_span(tokens: list[str]) -> list[str]:
    """Longest distinctive product-name span, or [].

    Kept for sticky single-product conversation scope; comparison retrieval uses
    ``_product_spans`` / ``named_product_labels`` instead.
    """
    spans = _product_spans(tokens)
    if not spans:
        return []
    return max(spans, key=len)


def named_product_labels(query: str, *, titles: list[str] | None = None) -> list[str]:
    """Surface-form product labels named in ``query``, in appearance order.

    Prefers full indexed document titles when the query mentions them (even
    without a ``bảo hiểm`` cue — e.g. "an khang như ý và an lộc vững bền").
    Falls back to cue-phrase spans from the query text.
    """
    if not query.strip():
        return []

    known_titles = titles if titles is not None else _load_indexed_titles()
    from_titles = mentioned_doc_titles(query, known_titles)
    if len(from_titles) >= 2:
        return from_titles

    folded = _fold_tokens(query)
    spans = _product_spans(folded)
    if not spans:
        return from_titles

    raw_words = re.findall(r"\w+", query, flags=re.UNICODE)
    labels: list[str] = []
    used_starts: set[int] = set()
    for span in spans:
        label: str | None = None
        for i in range(len(folded) - len(span) + 1):
            if i in used_starts:
                continue
            if _span_matches_at(folded, i, span):
                end = _span_end_index(folded, i, span)
                if len(raw_words) == len(folded):
                    label = " ".join(raw_words[i:end])
                else:
                    label = " ".join(span)
                used_starts.add(i)
                break
        labels.append(label or " ".join(span))

    # Cue spans win when they found more products than title matching
    # (title matching can miss short suffixes like "Ý").
    if len(labels) >= 2:
        return labels
    return from_titles or labels


def named_product_labels_from_queries(
    query: str,
    standalone_query: str,
    *,
    titles: list[str] | None = None,
) -> list[str]:
    """Union of product labels detected in either the raw or rewritten question.

    Query rewrite sometimes drops a product name on follow-up turns ("tóm tắt
    bảo hiểm an tâm hoạch định" → "Tóm tắt sản phẩm liên kết chung") while the
    raw user text still names it — unioning both forms keeps retrieval filters,
    prompt flags, and post-generation cleanup aligned.
    """
    known = titles if titles is not None else _load_indexed_titles()
    seen: set[str] = set()
    out: list[str] = []
    for text in (query, standalone_query):
        if not text.strip():
            continue
        for label in named_product_labels(text, titles=known):
            key = label.casefold()
            if key not in seen:
                seen.add(key)
                out.append(label)
    return out


def is_product_summary_turn(query: str, standalone_query: str) -> bool:
    """True when either the raw or rewritten question asks for a product overview."""
    return is_product_summary_query(query) or is_product_summary_query(standalone_query)


def query_names_absent_product_from_queries(
    query: str,
    standalone_query: str,
    hit_titles: list[str],
    *,
    known_titles: list[str] | None = None,
) -> bool:
    """Product-scope guard using both raw and rewritten question text."""
    return query_names_absent_product(
        standalone_query, hit_titles, known_titles=known_titles
    ) or (
        query.strip() != standalone_query.strip()
        and query_names_absent_product(query, hit_titles, known_titles=known_titles)
    )


def _span_matches_at(tokens: list[str], start: int, span: list[str]) -> bool:
    """True when ``span``'s distinctive tokens appear in order from ``start``."""
    k = 0
    j = start
    while j < len(tokens) and k < len(span):
        if tokens[j] == span[k]:
            k += 1
            j += 1
        elif tokens[j] in _NAME_BRIDGES and k > 0:
            j += 1
        else:
            return False
    return k == len(span)


def _span_end_index(tokens: list[str], start: int, span: list[str]) -> int:
    """Index just past the last token of ``span`` aligned at ``start``."""
    k = 0
    j = start
    while j < len(tokens) and k < len(span):
        if tokens[j] == span[k]:
            k += 1
            j += 1
        elif tokens[j] in _NAME_BRIDGES and k > 0:
            j += 1
        else:
            break
    return j


def title_covers_product(
    title: str,
    product_label: str,
    *,
    known_titles: list[str] | None = None,
) -> bool:
    """True when ``title`` is a document for ``product_label``.

    When ``known_titles`` is supplied, matching is corpus-aware (requires enough
    distinctive-token overlap — a lone shared prefix like "An Tâm" is not enough).
    Without it, falls back to any shared distinctive token (legacy tests).
    """
    if known_titles:
        resolved = resolve_product_titles(product_label, known_titles)
        if resolved:
            title_cf = title.casefold()
            return any(t.casefold() == title_cf for t in resolved)
        return False
    label_toks = _distinctive_title_tokens(product_label)
    if not label_toks:
        return False
    title_toks = set(_fold_tokens(title))
    return bool(label_toks & title_toks)


def _quoted_product_name(title: str) -> str | None:
    """Product name inside quotes in a policy title, if any."""
    match = re.search(r'"([^"]+)"', title)
    return match.group(1).strip() if match else None


def resolve_product_titles(product_label: str, known_titles: list[str]) -> list[str]:
    """Indexed document titles that ``product_label`` refers to."""
    if not product_label.strip() or not known_titles:
        return []
    from_titles = mentioned_doc_titles(product_label, known_titles)
    if from_titles:
        return from_titles
    label_folded = _fold(product_label)
    for title in known_titles:
        quoted = _quoted_product_name(title)
        if quoted and _fold(quoted) in label_folded:
            return [title]
    label_tokens = {t for t in _fold_tokens(product_label) if t not in _GENERIC}
    if not label_tokens:
        return []
    matches: list[tuple[int, str]] = []
    for title in known_titles:
        t_dist = _distinctive_title_tokens(title, other_titles=known_titles)
        overlap = label_tokens & t_dist
        if not overlap:
            continue
        needed = max(
            2,
            (len(label_tokens) + 1) // 2,
            (len(t_dist) + 1) // 2,
        )
        needed = min(needed, len(label_tokens), len(t_dist))
        if len(overlap) < needed:
            if not (len(t_dist) == 1 and overlap == t_dist and len(label_tokens) >= 2):
                continue
        if overlap <= _TITLE_ONLY_CANDIDATES:
            continue
        if overlap <= frozenset({"gia", "dinh"}):
            continue
        label_tok_list = _fold_tokens(product_label)
        positions = [i for i, tok in enumerate(label_tok_list) if tok in overlap]
        pos = min(positions) if positions else 0
        matches.append((pos, title))
    matches.sort(key=lambda item: item[0])
    out: list[str] = []
    seen: set[str] = set()
    for _, title in matches:
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(title)
    return out


# Product-TYPE connectors ("Trọn Đời" = whole life, "Liên Kết" = universal
# life) that are ALWAYS generic when parsing a QUERY (_collect_name_run,
# _product_spans, conversation_scope's query-side helpers all keep using the
# full _GENERIC, unchanged) but that can double as a product's own
# brand-defining words when scoring a document TITLE's distinctiveness. In
# this corpus "Trọn Đời"/"Liên Kết" each occur only within their own single
# product's title (once as category, once as brand) — never across a
# DIFFERENT product. _distinctive_title_tokens' dynamic check (below)
# restores them as candidates ONLY when they're not also shared by other
# titles, so a future second "Trọn Đời" product correctly makes them
# non-distinctive again for both, the same way AGENT1's static list already
# handles corpus-wide boilerplate ("quy"/"tắc"/"điều"/"khoản").
_TITLE_ONLY_CANDIDATES: frozenset[str] = frozenset({"tron", "doi", "lien", "ket"})


def _distinctive_title_tokens(
    title: str, *, other_titles: list[str] | None = None
) -> set[str]:
    """Non-generic, corpus-distinctive tokens that identify a document title.

    Keeps single-character tokens (e.g. ``ý``/``y`` in "An Khang Như Ý") —
    dropping them left some real product titles with only one usable token
    and made informal nickname matching fail.

    ``other_titles`` (optional — pass the full indexed-title list to enable
    this): a token shared by half or more of the OTHER titles is corpus-wide
    boilerplate, not product-distinctive, even if it isn't in the static
    ``_GENERIC``/``_TITLE_ONLY_CANDIDATES`` lists — this is what lets a
    token like "trọn"/"đời" count as distinctive for the one product that
    actually uses it as a brand word (NEW1/AGENT4, 2026-08-06 audit: "An
    Bình Trọn Đời" and "An Phú Liên Kết" each reduced to a SINGLE static-only
    distinctive token, {"binh"}/{"phu"}, below the ≥2-token floor
    ``mentioned_doc_titles`` needs — live-reproduced as a flat refusal on a
    3-product summary request naming both by name).
    """
    base_generic = _GENERIC - _TITLE_ONLY_CANDIDATES
    own = {t for t in _fold_tokens(title) if t not in base_generic}
    others = [t for t in (other_titles or ()) if t != title]
    if not others:
        return own
    threshold = max(1, (len(others) + 1) // 2)
    shared_counts: Counter[str] = Counter()
    for other in others:
        shared_counts.update(set(_fold_tokens(other)) - base_generic)
    return {t for t in own if shared_counts.get(t, 0) < threshold}


def mentioned_doc_titles(query: str, titles: list[str]) -> list[str]:
    """Indexed doc titles whose distinctive name tokens appear in ``query``.

    Catches informal mentions that omit the ``bảo hiểm`` / ``sản phẩm`` cue
    ("so sánh an khang như ý và an lộc vững bền"). Requires ≥2 distinctive
    token overlaps so a lone shared word cannot claim a title. Ordered by the
    earliest distinctive-token position in the query.

    The overlap must also include at least one token outside
    ``_TITLE_ONLY_CANDIDATES`` (a genuinely brand-unique word, e.g. "binh" for
    "An Bình Trọn Đời") — not just promoted category words like "trọn"/"đời"
    on their own. Those words are real, common Vietnamese insurance
    terminology ("niên kim nhân thọ trọn đời" = whole-life annuity, a generic
    actuarial phrase) that appears in unrelated formula/glossary content, not
    only in this one product's brand name. Without this guard, Day 6's
    corpus-relative fix for AGENT4 (which restores "trọn"/"đời" as
    title-distinctive precisely because no OTHER indexed title shares them)
    over-fires on any query using that generic phrase, regardless of whether
    it names the product at all — live-reproduced 2026-08-07 (Day 7 full-gate
    rerun): q12/q15 (annuity formula questions, no product named) both
    false-refused because "trọn đời" alone matched "An Bình Trọn Đời".
    """
    if not query.strip() or not titles:
        return []
    q_toks = _fold_tokens(query)
    q_set = set(q_toks)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for title in titles:
        dist = _distinctive_title_tokens(title, other_titles=titles)
        if len(dist) < 2:
            continue
        needed = max(2, (len(dist) + 1) // 2)
        overlap = dist & q_set
        if len(overlap) < needed:
            continue
        if overlap <= _TITLE_ONLY_CANDIDATES:
            continue
        if overlap <= frozenset({"gia", "dinh"}):
            continue
        key = title.casefold()
        if key in seen:
            continue
        positions = [i for i, t in enumerate(q_toks) if t in overlap]
        pos = min(positions) if positions else 0
        seen.add(key)
        scored.append((pos, title))
    scored.sort(key=lambda item: item[0])
    return [title for _, title in scored]


def query_names_absent_product(
    query: str,
    hit_titles: list[str],
    *,
    known_titles: list[str] | None = None,
) -> bool:
    """True when the query names a KNOWN product that is absent from the hits.

    "Known" means the query resolves — via ``mentioned_doc_titles``, i.e. a ≥2
    distinctive-token overlap — to at least one *indexed* document title. That
    strong-match requirement is the whole point of this revision: the earlier
    version read any non-stopword token after a cue phrase ("bảo hiểm", "sản
    phẩm", ...) as a product name, so ordinary questions like "...bảo hiểm gồm
    những **bước** nào?" or "...cần những **giấy tờ** gì?" fabricated a product
    ("bước", "giấy tờ") and refused an answerable question. A common noun does
    not strongly match any product title, so it can no longer trigger a refusal.

    We only refuse when the query genuinely points at a product the corpus
    contains AND none of the retrieved documents are that product — the
    wrong-product case this guard exists for (e.g. asking about product A while
    only product B was retrieved). For a comparison naming A and B, refuses only
    when BOTH named products are absent from the retrieved titles.

    Trade-off (intended): a product ABSENT from the whole index — deleted, or
    carried only under an abbreviated title sharing no token with its spelled-out
    name — no longer trips this deterministic guard. Those cases fall back to the
    system prompt's own wrong-product refusal (rule 1). This narrowing is
    deliberate: it removes the false refusals, relying on the prompt rather than
    code for the rarer absent-from-corpus case.

    ``known_titles`` defaults to the currently indexed titles (loaded from
    Qdrant); injected in tests.
    """
    known = known_titles if known_titles is not None else _load_indexed_titles()
    named = mentioned_doc_titles(query, known)
    if not named:
        return False
    hit_set = {title.casefold() for title in hit_titles}
    return all(title.casefold() not in hit_set for title in named)


def _load_indexed_titles() -> list[str]:
    """Best-effort titles from Qdrant; empty when the store is unavailable."""
    try:
        from app.ingestion import indexer

        return [d.doc_title for d in indexer.list_documents()]
    except Exception:  # pragma: no cover - Qdrant locked/offline
        return []


def filter_hits_to_named_products(
    query: str,
    hits: list[Hit],
    *,
    known_titles: list[str] | None = None,
    standalone_query: str | None = None,
) -> list[Hit]:
    """Drop policy chunks from products other than the one(s) named in ``query``.

    Shared corpus material (glossary, guides, procedures, ...) is kept so
    actuarial questions about a named product can still cite the dictionary.
    When a product is named but no matching policy survives, shared non-policy
    chunks are kept rather than falling back to foreign policy docs.
    """
    if not hits:
        return hits
    known = known_titles if known_titles is not None else _load_indexed_titles()
    if not known:
        return hits
    if standalone_query and standalone_query.strip() != query.strip():
        labels = named_product_labels_from_queries(
            query, standalone_query, titles=known
        )
    else:
        labels = named_product_labels(query, titles=known) if query.strip() else []
    if not labels:
        return hits

    target_titles: list[str] = []
    seen_targets: set[str] = set()
    for label in labels:
        for title in resolve_product_titles(label, known):
            key = title.casefold()
            if key not in seen_targets:
                seen_targets.add(key)
                target_titles.append(title)
    if not target_titles:
        return hits

    target_cf = {t.casefold() for t in target_titles}
    known_cf = {t.casefold() for t in known}
    filtered: list[Hit] = []
    for hit in hits:
        dt_cf = hit.payload.doc_title.casefold()
        if dt_cf in target_cf:
            filtered.append(hit)
            continue
        if hit.payload.doc_type != DocType.POLICY:
            filtered.append(hit)
            continue
        if dt_cf in known_cf:
            continue
        filtered.append(hit)

    if filtered:
        return filtered
    # Named product(s) resolved but every policy hit was foreign — keep shared
    # corpus (glossary, procedures) rather than restoring wrong-product policies.
    shared = [h for h in hits if h.payload.doc_type != DocType.POLICY]
    return shared if shared else hits


_SUMMARY_MARKERS = (
    "tom tat",
    "tong quan",
    "gioi thieu",
    "overview",
    "summary",
)


def is_product_summary_query(query: str) -> bool:
    """True when the user asks for a product overview / summary."""
    from app.text_utils import fold_text

    folded = fold_text(query)
    if any(marker in folded for marker in _SUMMARY_MARKERS):
        return True
    # "chi tiết" alone also matches benefit-list questions — require "tóm tắt".
    return "chi tiet" in folded and "tom tat" in folded


def is_glossary_title(title: str) -> bool:
    """True for shared actuarial dictionary / reference titles (not a product policy)."""
    from app.text_utils import fold_text

    folded = fold_text(title)
    return "tu dien" in folded or "thuat ngu" in folded or "dinh phi" in folded


def is_shared_corpus_hit(hit: Hit) -> bool:
    """Glossary/reference chunks — fine for actuarial Q&A, not product summaries."""
    if hit.payload.doc_type in (DocType.GLOSSARY, DocType.REFERENCE):
        return True
    return is_glossary_title(hit.payload.doc_title)


def filter_hits_for_product_summary(
    hits: list[Hit],
    product_labels: list[str],
    *,
    known_titles: list[str] | None = None,
) -> list[Hit]:
    """Drop glossary/reference chunks when summarizing a named product.

    Keeps them only when no policy chunk for the product survived filtering —
    better a thin answer than one sourced entirely from the pricing dictionary.
    """
    if len(product_labels) != 1 or not hits:
        return hits
    known = known_titles if known_titles is not None else _load_indexed_titles()
    target_titles = resolve_product_titles(product_labels[0], known)
    if not target_titles:
        return hits
    target_cf = {t.casefold() for t in target_titles}
    policy = [
        h
        for h in hits
        if h.payload.doc_type == DocType.POLICY
        and h.payload.doc_title.casefold() in target_cf
    ]
    if not policy:
        return hits
    return [
        h
        for h in hits
        if h.payload.doc_title.casefold() in target_cf or not is_shared_corpus_hit(h)
    ]


def policy_hits_first(
    hits: list[Hit],
    product_labels: list[str],
    *,
    known_titles: list[str] | None = None,
) -> list[Hit]:
    """Move target-product policy chunks ahead of glossary material for rerank order."""
    if len(product_labels) != 1 or not hits:
        return hits
    known = known_titles if known_titles is not None else _load_indexed_titles()
    target_cf = {t.casefold() for t in resolve_product_titles(product_labels[0], known)}
    primary = [
        h
        for h in hits
        if h.payload.doc_type == DocType.POLICY
        and h.payload.doc_title.casefold() in target_cf
    ]
    rest = [h for h in hits if h not in primary]
    return primary + rest


def backfill_product_policy_hits(
    hits: list[Hit],
    product_labels: list[str],
    *,
    search_fn: Callable[[str, list[str]], list[Hit]],
    budget: int | None = None,
    known_titles: list[str] | None = None,
    docs: list[tuple[str, str]] | None = None,
    max_added: int = 3,
) -> list[Hit]:
    """Fetch product-policy chunks when a summary turn retrieved only glossary."""
    from app.retrieval.comparison import product_doc_ids

    if len(product_labels) != 1:
        return hits
    known = known_titles if known_titles is not None else _load_indexed_titles()
    target_titles = resolve_product_titles(product_labels[0], known)
    target_cf = {t.casefold() for t in target_titles}
    if not target_cf:
        return hits
    has_policy = any(
        h.payload.doc_type == DocType.POLICY
        and h.payload.doc_title.casefold() in target_cf
        for h in hits
    )
    if has_policy:
        return hits
    doc_list = docs if docs is not None else []
    if not doc_list:
        try:
            from app.ingestion import indexer

            doc_list = [(d.doc_id, d.doc_title) for d in indexer.list_documents()]
        except Exception:  # pragma: no cover
            return hits
    doc_ids = product_doc_ids(product_labels[0], doc_list)
    if not doc_ids:
        return hits
    seen = {h.point_id for h in hits}
    label = product_labels[0]
    added: list[Hit] = []
    for q in (f"tóm tắt {label}", f"quyền lợi {label}", label):
        for hit in search_fn(q, doc_ids):
            if hit.point_id in seen:
                continue
            if hit.payload.doc_title.casefold() not in target_cf:
                continue
            seen.add(hit.point_id)
            added.append(hit)
            if len(added) >= max_added:
                break
        if len(added) >= max_added:
            break
    if not added:
        return hits
    over = len(hits) + len(added) - budget if budget else 0
    if over <= 0:
        return hits + added
    kept = hits[: max(0, len(hits) - over)]
    return kept + added
