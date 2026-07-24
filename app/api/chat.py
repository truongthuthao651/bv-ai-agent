"""OpenAI-compatible chat endpoint.

``POST /v1/chat/completions`` implements the full query flow (skill, sections
5-6): standalone-question rewrite -> glossary expansion -> hybrid search ->
rerank -> generation. Streams SSE in OpenAI format by default so Open WebUI
works unmodified; also supports ``stream: false`` for plain API clients.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.config.settings import settings
from app.generation import generator
from app.generation.advisory import is_advisory_query
from app.generation.prompts import REFUSAL_MESSAGE
from app.query_timing import TimingContext
from app.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Hit,
    ModelCard,
    ModelList,
)
from app.retrieval.comparison import is_multi_product_query, retrieve_multi_product
from app.retrieval.conversation_scope import active_scope, cited_titles_in_history
from app.retrieval.metric_guard import filter_metric_mismatch
from app.retrieval.product_scope import query_names_absent_product
from app.retrieval.query_expansion import expand_query
from app.retrieval.query_rewrite import rewrite_standalone
from app.retrieval.reranker import rerank
from app.retrieval.retriever import hybrid_search
from app.retrieval.spellcheck import (
    corrected_query_after_confirmation,
    is_affirmation,
    is_confirmation_prompt,
    maybe_suggest_correction,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["chat"])


@router.get("/models", response_model=ModelList)
async def list_models() -> ModelList:
    """Advertise the single branded assistant model.

    Open WebUI calls this to populate its model dropdown; without it our backend
    contributes no selectable model and the chat UI stays empty. The id/label are
    branding only — ``chat_completions`` always serves ``settings.chat_model``.
    """
    return ModelList(
        data=[
            ModelCard(
                id=settings.assistant_model_id,
                created=int(time.time()),
                name=settings.assistant_name,
            )
        ]
    )


# Opening text of Open WebUI's built-in task prompts (title/tag generation,
# etc. — pinned image open-webui:0.5.4, so these templates are stable). Such
# requests arrive on this same endpoint and must bypass the RAG pipeline: a
# full retrieval+rerank costs minutes on CPU, and the grounded system prompt
# would turn every chat title into the refusal sentence.
_META_TASK_PREFIXES = (
    "### Task:",
    "Create a concise, 3-5 word title",
)


def _is_meta_task(query: str) -> bool:
    """True for Open WebUI meta-requests (title/tags), not real user questions."""
    return query.lstrip().startswith(_META_TASK_PREFIXES)


def _static_response(
    request: ChatCompletionRequest,
    text: str,
    *,
    timing: TimingContext | None = None,
):
    """Return a fixed answer as SSE (``stream``) or a plain completion.

    Shared by every deterministic-answer path (meta-task, spellcheck
    clarification, product-scope refusal) so they all frame the response the
    same way. ``timing`` is passed only for the post-retrieval refusals (which
    really did take the retrieval time); the instant pre-retrieval paths leave
    it ``None`` so no "0s" footer appears.
    """
    if request.stream:
        return StreamingResponse(
            generator.stream_static_answer(text, timing=timing),
            media_type="text/event-stream",
        )
    footer = ""
    if timing is not None:
        from app.query_timing import log_query_timing, response_time_footer

        footer = response_time_footer(timing)
        log_query_timing(timing, answer_chars=len(text))
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=settings.chat_model,
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=text + footer)
            )
        ],
    )


def _split_request(request: ChatCompletionRequest) -> tuple[str, list[ChatMessage]]:
    """Split ``messages`` into (latest user turn, prior history)."""
    if not request.messages:
        return "", []
    *history, last = request.messages
    return last.content, history


def _resolve_confirmation(
    query: str, history: list[ChatMessage]
) -> tuple[str, list[ChatMessage], bool]:
    """Route a bare confirmation of a prior spellcheck prompt back to its question.

    The typo gate spans two turns but the endpoint is stateless: when the last
    assistant turn was one of our clarification messages and the user simply
    confirms it ("đúng"), retrieving on the word "đúng" finds nothing. Instead we
    replay the *original* question with suggested corrections applied, drop that
    resolved exchange from history, and signal the caller to skip the gate so it
    can't re-trigger the same clarification in a loop.

    Returns ``(query, history, skip_spellcheck)`` unchanged when this isn't a
    confirmation continuation.
    """
    if (
        len(history) >= 2
        and history[-1].role == "assistant"
        and history[-2].role == "user"
        and is_confirmation_prompt(history[-1].content)
        and is_affirmation(query)
    ):
        original = history[-2].content
        corrected = corrected_query_after_confirmation(original)
        return corrected, history[:-2], True
    return query, history, False


def _advisory_followup_labels(query: str, history: list[ChatMessage]) -> list[str]:
    """Products still under comparison for an advisory follow-up that names none.

    "KH sẽ chọn sản phẩm nào nhỉ" carries no product name, so single-scope
    retrieval pins one of the two products just compared and the other's
    benefits never reach the context — leaving the model nothing to weigh.
    Recovering the titles cited by the previous turns keeps every candidate in
    play. Empty (so nothing changes) unless this really is an advisory turn
    following a multi-document answer.
    """
    if not settings.advisory_mode_enabled or not settings.comparison_retrieval_enabled:
        return []
    if not is_advisory_query(query) or is_multi_product_query(query):
        return []
    titles = cited_titles_in_history(history)[: settings.comparison_max_products]
    return titles if len(titles) >= 2 else []


def _retrieve(
    query: str, history: list[ChatMessage]
) -> tuple[str, list[Hit], list[str], list[Hit]]:
    """Run rewrite -> expansion -> hybrid search -> rerank; each stage is self-gating.

    Multi-product (comparison) queries take a per-product search path so each
    named product keeps a fair share of the context budget. Logs per-stage wall
    time so slow answers can be attributed to a stage instead of guessed at.
    eval/run_ragas.py drives the SAME pipeline through ``plan_response`` (it no
    longer re-implements this flow), so retrieval metrics reflect production.

    Returns ``(standalone_query, hits, followup_labels, fused)``: ``fused`` is the
    pre-rerank hybrid pool (empty on the per-product path), returned so callers
    can report search-vs-rerank quality; ``labels`` are the carried-over
    comparison products (empty for ordinary turns).
    """
    # Sticky single-product scope biases rewrite toward one title; skip it when
    # the user already named ≥2 products (comparison / side-by-side questions)
    # or is following up on a comparison of several cited documents.
    followup_labels = _advisory_followup_labels(query, history)
    multi = settings.comparison_retrieval_enabled and (
        is_multi_product_query(query) or bool(followup_labels)
    )
    scope = (
        None
        if multi
        else (active_scope(history) if settings.conversation_scope_enabled else None)
    )
    t0 = time.perf_counter()
    standalone_query = rewrite_standalone(history, query, scope=scope)
    t1 = time.perf_counter()

    # Re-check on the rewritten question (rewrite may surface a second product
    # from history, or drop one — prefer the standalone form for routing).
    named_multi = settings.comparison_retrieval_enabled and is_multi_product_query(
        standalone_query
    )
    # Carried-over labels only apply when the rewritten question still names no
    # products of its own (otherwise the query text is the better signal).
    explicit_labels = followup_labels if not named_multi else []
    use_multi = named_multi or bool(explicit_labels)
    if use_multi:
        t2 = time.perf_counter()

        def _rerank_cap(q: str, raw: list[Hit], top_k: int) -> list[Hit]:
            return rerank(q, raw, top_k=top_k)

        def _search_scoped(q: str, doc_ids: list[str] | None) -> list[Hit]:
            # Scoping by doc_id gives each product a full retrieve_top_k pool of
            # its own documents instead of a share of one corpus-wide pool.
            filters = {"doc_id": doc_ids} if doc_ids else None
            return hybrid_search(q, filters=filters)

        hits = retrieve_multi_product(
            standalone_query,
            search_fn=_search_scoped,
            rerank_fn=_rerank_cap,
            expand_fn=expand_query,
            labels=explicit_labels or None,
        )
        # No single fused pool on the per-product path.
        fused: list[Hit] = []
        # Per-product path folds expand+search+rerank into one timed block.
        t3 = t2
        t4 = time.perf_counter()
    else:
        search_query = expand_query(standalone_query)
        t2 = time.perf_counter()
        fused = hybrid_search(search_query)
        t3 = time.perf_counter()
        hits = rerank(standalone_query, fused)
        t4 = time.perf_counter()

    if settings.metric_guard_enabled:
        before = len(hits)
        hits = filter_metric_mismatch(standalone_query, hits)
        if len(hits) != before:
            logger.info(
                "metric guard: dropped %d fee/interest hit(s) for benefit-payout query",
                before - len(hits),
            )
    t5 = time.perf_counter()
    logger.info(
        "retrieval timings: rewrite=%.0fms expand=%.0fms search=%.0fms "
        "rerank=%.0fms metric_guard=%.0fms hits=%d scope=%s multi=%s carried=%s",
        (t1 - t0) * 1000,
        (t2 - t1) * 1000,
        (t3 - t2) * 1000,
        (t4 - t3) * 1000,
        (t5 - t4) * 1000,
        len(hits),
        scope or "-",
        use_multi,
        explicit_labels or "-",
    )
    return standalone_query, hits, explicit_labels, fused


@dataclass
class ResponsePlan:
    """What to answer for one turn, decided by the full pipeline (no I/O left).

    ``kind`` selects how the caller renders it:
    ``meta`` (a UI title/tag task — caller generates a plain answer),
    ``clarification`` / ``refusal`` (static ``text``),
    ``hybrid`` (no-context general-knowledge answer),
    ``grounded`` (answer from ``hits``; ``advisory`` picks the synthesis prompt).

    Extracting this from the HTTP handler lets ``eval/run_ragas.py`` exercise the
    EXACT production decision tree — spellcheck gate, product-scope guard,
    hybrid/refusal fallback, advisory routing — instead of a drifting copy, which
    is what let false refusals slip past the old eval.
    """

    kind: str
    query: str
    history: list[ChatMessage]
    standalone_query: str = ""
    text: str | None = None
    hits: list[Hit] = field(default_factory=list)
    fused: list[Hit] = field(default_factory=list)
    advisory: bool = False


def plan_response(query: str, history: list[ChatMessage]) -> ResponsePlan:
    """Run the full pre-generation decision tree and return what to answer.

    Pure of HTTP/streaming concerns and synchronous, so it runs in one threadpool
    hop for the endpoint and is called directly, in-process, by the eval harness.
    """
    # A bare confirmation of a prior spellcheck prompt replays the original
    # question and skips the gate (so we don't re-ask in a loop).
    query, history, skip_spellcheck = _resolve_confirmation(query, history)

    # Open WebUI meta-tasks (chat titles/tags) skip retrieval entirely.
    if _is_meta_task(query):
        return ResponsePlan(kind="meta", query=query, history=history)

    # Ask before answering on a likely typo/garbled term rather than guessing.
    if not skip_spellcheck:
        clarification = maybe_suggest_correction(query)
        if clarification:
            return ResponsePlan(
                kind="clarification", query=query, history=history, text=clarification
            )

    standalone_query, hits, carried_labels, fused = _retrieve(query, history)

    # Product-scope guard: the query names a specific product but every retrieved
    # document is a DIFFERENT product. Refuse rather than answer from — and cite —
    # the wrong product (a hard refusal: we DO have documents, just not this one).
    if (
        hits
        and settings.product_scope_guard_enabled
        and query_names_absent_product(
            standalone_query, [hit.payload.doc_title for hit in hits]
        )
    ):
        logger.info(
            "product-scope guard: named product absent from %d retrieved doc(s); "
            "refusing",
            len(hits),
        )
        return ResponsePlan(
            kind="refusal",
            query=query,
            history=history,
            standalone_query=standalone_query,
            text=REFUSAL_MESSAGE,
            hits=hits,
            fused=fused,
        )

    # No hit survived the reranker's floor: fall back to a clearly-labeled
    # general-knowledge answer or refuse deterministically. Scoped follow-ups
    # (prior turn pinned a company product/document) always refuse.
    if not hits:
        scoped = bool(settings.conversation_scope_enabled and active_scope(history))
        if not settings.hybrid_fallback_enabled or scoped:
            if scoped:
                logger.info(
                    "hybrid fallback skipped: conversation scope is set "
                    "(company-document follow-up)"
                )
            return ResponsePlan(
                kind="refusal",
                query=query,
                history=history,
                standalone_query=standalone_query,
                text=REFUSAL_MESSAGE,
                fused=fused,
            )
        return ResponsePlan(
            kind="hybrid",
            query=query,
            history=history,
            standalone_query=standalone_query,
            fused=fused,
        )

    # Advisory / synthesis turn: the documents hold the facts but never the
    # conclusion asked for ("KH sẽ chọn sản phẩm nào?"), which the strict prompt
    # refuses outright — same context, a prompt that may reason across it.
    advisory = settings.advisory_mode_enabled and (
        bool(carried_labels)
        or is_advisory_query(query)
        or is_advisory_query(standalone_query)
    )
    if advisory:
        logger.info("advisory mode: synthesizing over %d hit(s)", len(hits))
    return ResponsePlan(
        kind="grounded",
        query=query,
        history=history,
        standalone_query=standalone_query,
        hits=hits,
        fused=fused,
        advisory=advisory,
    )


@router.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Answer a chat request, grounded only in retrieved document chunks."""
    # End-to-end timer: everything the user waits for (retrieval + generation)
    # is measured from here, so the "⏱ Thời gian trả lời" footer and the timing
    # log reflect the real answer latency, not just token generation.
    started_at = time.perf_counter()
    query, history = _split_request(request)
    plan = await run_in_threadpool(plan_response, query, history)

    if plan.kind == "meta":
        answer = await run_in_threadpool(generator.generate_plain, plan.query)
        return _static_response(request, answer)
    if plan.kind == "clarification":
        return _static_response(request, plan.text)
    if plan.kind == "refusal":
        return _static_response(
            request,
            plan.text,
            timing=TimingContext(
                started_at,
                "refusal",
                n_hits=len(plan.hits),
                query_chars=len(plan.standalone_query),
                stream=request.stream,
            ),
        )

    if plan.kind == "hybrid":
        timing = TimingContext(
            started_at,
            "hybrid",
            n_hits=0,
            query_chars=len(plan.standalone_query),
            stream=request.stream,
        )
        if request.stream:
            return StreamingResponse(
                generator.stream_hybrid_answer(
                    plan.standalone_query, plan.history, timing=timing
                ),
                media_type="text/event-stream",
            )
        answer = await run_in_threadpool(
            generator.generate_hybrid_answer,
            plan.standalone_query,
            plan.history,
            timing=timing,
        )
    else:  # grounded
        timing = TimingContext(
            started_at,
            "advisory" if plan.advisory else "grounded",
            n_hits=len(plan.hits),
            query_chars=len(plan.standalone_query),
            stream=request.stream,
        )
        if request.stream:
            return StreamingResponse(
                generator.stream_answer(
                    plan.standalone_query,
                    plan.hits,
                    plan.history,
                    advisory=plan.advisory,
                    timing=timing,
                ),
                media_type="text/event-stream",
            )
        answer = await run_in_threadpool(
            generator.generate_answer,
            plan.standalone_query,
            plan.hits,
            plan.history,
            plan.advisory,
            timing=timing,
        )
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=settings.chat_model,
        choices=[
            ChatCompletionChoice(message=ChatMessage(role="assistant", content=answer))
        ],
    )
