# Phase 4 — Chatbot: streaming, latency, chat UX

Date: 2026-08-08. Read-only phase. All findings from (a) reading
`app/api/chat.py`, `app/generation/generator.py`, `app/query_timing.py`,
`frontend/src/chat/{api,ChatScreen,ChatMessage,Composer,markdown}.jsx`, and (b) 10 real,
timed queries against the **running** `/v1/chat/completions` endpoint (server already up,
Ollama+Qdrant healthy) as the employee demo account — 8 single-turn + one 2-turn follow-up
conversation. Raw results: `phase4_results.jsonl` (kept in scratch, not committed — contains
full answer text; the timings and answer previews below are the citable evidence).

## 4.1 Streaming mechanics

**SSE framing**: correct OpenAI-format `data: {...}\n\n` chunks ending in `data: [DONE]\n\n`
(`app/generation/generator.py` `_sse_chunk`), consumed by a straightforward
`ReadableStream.getReader()` + manual `\n\n`-split buffer in `frontend/src/chat/api.js:38-51` —
no intermediate buffering layer found between Ollama → FastAPI → browser (`httpx.AsyncClient`
streams via `aiter_lines()`, `StreamingResponse` streams the async generator directly).

**Math-delimiter safety, confirmed both by code and by live output**: `frontend/src/chat/
markdown.jsx:51`'s `splitMath` regex (`/\$\$([^$]+?)\$\$|\$([^$\n]+?)\$/g`) requires a *closing*
`$$`/`$` to match at all — an incomplete `$$...` mid-stream (closing delimiter not arrived yet)
is left as literal text rather than partially rendered, so there is no flash of broken KaTeX
while a formula is still streaming in. The `formula` query below streamed a real display
equation (`$$\ddot{a}_{x:\overline{n}|} = ...$$`) and rendered correctly once complete.

**Cancellation — CONFIRMED ABSENT, P1, S/M effort.** `frontend/src/chat/api.js:26-51`
(`askStreaming`) calls `fetch()` with no `AbortController`/`signal`, and
`frontend/src/chat/ChatScreen.jsx` (full file read) has no "stop generating" button anywhere —
the composer only shows a disabled send button while `busy` is true
(`frontend/src/chat/Composer.jsx:58-72`). Given the measured latencies below (single answers
regularly taking 20-50 seconds), an employee who realizes they asked the wrong question, or
started the wrong follow-up, has **no way to stop it** short of closing the tab — and even then,
the server has no `request.is_disconnected()` check in `app/generation/generator.py`'s streaming
loop, so whether closing the tab actually frees the Ollama call was not directly verifiable in
this pass (logged under Unverified suspicions). Fix: add an `AbortController` to `askStreaming`,
wire it to a visible "Dừng" button next to the composer while `busy`, and add an
`await request.is_disconnected()` check in the generation loop so an aborted client also frees
the backend/GPU. This is exactly the kind of fix the prompt's Wave 1 ("smoothness") category is
for — every long answer is currently a one-way commitment.

**Failure mid-stream**: not tested live (killing Ollama mid-request would have disrupted the
other agents' concurrent testing against the same shared server) — deferred to "Unverified
suspicions" below with the exact repro command. Code-level read: `app/generation/
generator.py:478-484` (`_stream_chat`) does catch `httpx.HTTPError` and yields
`_CONNECTION_ERROR_MESSAGE` as a normal content chunk before `stop`/`[DONE]` — so a
mid-generation Ollama crash *should* surface as readable Vietnamese text rather than a silently
truncated answer or a raw stack trace, which is the right shape if it works as read.

**Concurrency**: not load-tested (two tabs / two simultaneous users) — flagged as unverified.
`app/generation/generator.py:250-251`'s comment on `ollama_keep_alive` and the roadmap's own
"concurrency/global-lock redesign... belongs in a week with load-testing time" (deliberately
deferred per `docs/audit/roadmap.md`) both suggest this hasn't been exercised beyond
single-user testing anywhere in this project's history — inheriting that gap rather than
re-discovering it.

## 4.2 Timing & speed (measured, not estimated)

10 real queries via `POST /v1/chat/completions` (`stream: true`), timed client-side from request
send to first SSE content delta (TTFT) and to `[DONE]` (total):

| # | Query (category) | TTFT (s) | Total (s) | Answer chars |
|---|---|---|---|---|
| 1 | Chi trả STBH — An Tâm Bảo Vệ (`policy_qa`) | **47.17** | 49.17 | 2,766 |
| 2 | Công thức phí thuần tử kỳ (`formula`) | 12.19 | 19.05 | 540 |
| 3 | Tuổi hưu trí bổ sung — not in corpus (`refusal`, golden set) | 10.45 | 10.91 | 72 |
| 4 | $l_x$ tuổi 32 bảng tử vong (`table_lookup`) | 15.62 | 16.74 | 1,464 |
| 5 | Phí thuần là gì? (`definition`) | 9.68 | 11.26 | 1,857 |
| 6 | Suggested-prompt #1, full text (`suggested_prompt`) | 8.83 | 22.08 | 2,470 |
| 7 | Giá cổ phiếu Bảo Việt hôm nay? (`out_of_scope`) | 8.69 | 9.15 | 71 |
| 8 | Viết một bài thơ về mùa thu Hà Nội (`out_of_scope`, creative) | 9.64 | 13.92 | 412 |
| 9 | (turn 1) Chi trả STBH — An Tâm Bảo Vệ, repeat | 22.83 | 24.81 | ~300 |
| 10 | (turn 2, follow-up) "Còn nếu tử vong do tai nạn thì sao?" | 32.58 | 34.45 | ~350 |

**TTFT**: mean 17.8s, median 11.3s, range 8.7s–47.2s. **Total**: mean 21.2s, median 17.9s, range
9.2s–49.2s. The admin Overview dashboard (`audit/03-frontend.md` §3.5,
`admin-overview-desktop-light-full.png`) independently reports **p50 39.7s** over its own
(different, historical) sample window — both measurements agree on the same conclusion by
different methods: **this is a slow system**, TTFT and total time are close together (most of
the wait is retrieval+rerank+time-to-first-Ollama-token, not token-by-token generation speed),
and there is no query in either sample under ~9 seconds. Query #1's 47s TTFT was the very first
request of this test run — consistent with a one-time warm-up cost (embedder/reranker/Ollama
already loaded per `_warmup()` at server start, but the *first* real request of a session still
paid substantially more than every subsequent one in this small sample) rather than a
steady-state number; reported as observed, not excluded, per the evidence standard.

**Dominant cost**: not decomposed into retrieval-vs-rerank-vs-generation sub-timings in this
pass — `TimingContext` (`app/query_timing.py:44-75`) tracks only end-to-end `elapsed_s()` and,
on one code path only, `first_token_ms`. **Confirmed gap**: `first_token_ms` is populated on
exactly ONE of the four `log_query_timing(...)` call sites — `app/generation/
generator.py:463-469` (the plain grounded/advisory streaming path, `_stream_chat`). The other
three — `stream_static_answer` (`generator.py:396`, meta-tasks/instant refusals),
`_stream_gated_coverage` (`generator.py:586`, the coverage-gate verdict-checked path used for
every benefit/payout question), and whatever's at `generator.py:847` — never pass
`first_token_s`, so **coverage-gate answers (arguably the highest-stakes category — "was this
claim covered") have no TTFT data in the JSONL log at all**, only total elapsed time. This means
the admin dashboard's "Độ trễ trung vị (p50)" number is silently mixing "time to first token"
for some requests with "time to done" for others depending on which path answered — worth fixing
before trusting that KPI for anything more precise than a rough order of magnitude.

**Perceived speed**: `frontend/src/chat/ChatScreen.jsx` sends the user's message into the
message list immediately on submit (optimistic append, `nextMessages` at line ~52) and disables
the composer (`busy=true`) — so there's no dead air between clicking send and *something*
happening on screen. But there is no skeleton/spinner/"đang tìm..." indicator during the
8-47 second gap before the first token — the assistant's message bubble simply doesn't exist
until `onDelta` fires the first chunk (confirmed by reading `ChatScreen.jsx`'s `send()`: the
placeholder empty-text assistant message is added to `messages` immediately, so a bubble frame
DOES appear, but it renders as `renderMarkdown(body || " ")` — an essentially blank bubble
with nothing to signal "working" beyond its own existence — no dot-typing indicator, no elapsed
counter). Given TTFT routinely exceeds 10-20 seconds, this is the single highest-value UX fix
this phase surfaced: a "thinking…" state (even just three animated dots in the empty bubble)
would meaningfully change how the wait *feels* without touching backend latency at all.

## 4.3 Chat interface quality

**Composer** (`frontend/src/chat/Composer.jsx`, full file read): Enter-to-send / Shift+Enter-
newline correctly implemented with an `isComposing` guard (line 32: `!e.nativeEvent.isComposing`)
so IME composition (Vietnamese input methods that build characters over multiple keystrokes)
won't fire a premature send — a real, non-obvious correctness detail, done right. **Confirmed
gap**: no autogrow — `<textarea rows={2}>` (line 27) with `resize: "none"` and no
`scrollHeight`-driven height adjustment anywhere in the file, so a long multi-line question
scrolls inside a cramped 2-row box instead of the box growing (compare to the kit-standard
autogrow pattern the file's own header comment says was "ported from
`ui_kits/chatbot/ChatParts.jsx`" — worth checking whether the original had autogrow and it was
dropped, or never had it). No character/token limit found (client or server side). Disabled
state while streaming: correctly wired (`disabled` prop threaded through, confirmed in
`ChatScreen.jsx:145`).

**Citations — precise and clickable, confirmed live.** Every grounded answer in the 10-query
sample produced a real `**Nguồn tham khảo:**` block with `[n]` markers matching the prose, e.g.
query #5's answer cites `[1]` inline and lists
`[1] [Từ điển thuật ngữ định phí bảo hiểm](http://localhost:8000/documents/f575329d-.../view?section=ph%C3%AD%20thu%E1%BA%A7n)`
— a real, working, section-anchored URL to the source document, not a placeholder. Citation
numbers stayed stable and sequential across all 10 answers (no dangling `[3]` with only 2
sources listed, no duplicate numbering).

**Refusal message — CONFIRMED BROKEN, cross-verified independently by Phase 2's product audit
(`audit/02-product.md`) and by this phase's own live queries. P2, S effort, one-line fix.**
`frontend/src/chat/ChatMessage.jsx:116`: `const isRefusal = !streaming && text.trim() ===
REFUSAL_TEXT;` does an **exact-string** comparison against `"Tôi không tìm thấy thông tin trong
tài liệu."`. But `app/query_timing.py:86`'s `response_time_footer` unconditionally appends
`"\n\n_⏱ Thời gian trả lời: Ns_"` to every timed answer, refusals included — confirmed live in
queries #3 and #7 above, whose full raw text is:
```
Tôi không tìm thấy thông tin trong tài liệu.

_⏱ Thời gian trả lời: 11s_
```
`.trim()` on that string is never equal to `REFUSAL_TEXT` alone, so `isRefusal` is **always
false** in the browser, and `ChatMessage.jsx:88-94`'s friendlier `NoAnswer()` component — which
tells the employee to try naming the product or rephrasing — is **dead code**. What actually
renders is the raw refusal sentence run through the generic markdown path, immediately followed
by an italicized timing footer, with no recovery suggestion at all. Fix: strip the timing footer
before comparing (`text.replace(/\n\n_⏱.*$/, "").trim() === REFUSAL_TEXT`), or compare on
`.startsWith(REFUSAL_TEXT)` instead of exact equality.

**Scope creep in the "general knowledge" fallback — worth a product decision, P2.** Query #8
("Bạn hãy viết cho tôi một bài thơ về mùa thu Hà Nội" — "write me a poem about autumn in Hanoi")
was **not refused**. It went through the hybrid/general-knowledge path
(`app/generation/generator.py:591-607`, `stream_hybrid_answer`) and returned an actual four-line
poem, correctly disclaimed ("_Đây là kiến thức chung, không phải nội dung trích từ tài liệu nội
bộ của Bảo Việt Life..._"). Compare query #2 (a textbook actuarial formula question) taking the
same hybrid path with the same disclaimer — that one is a defensible use of "general knowledge
supplement" (it's still insurance-adjacent, textbook material a real actuary would know). A poem
about Hanoi in autumn is not insurance-adjacent by any reading, and demonstrates the hybrid
path's scope gate is "not found in retrieval" rather than "is this an insurance/actuarial
question" — meaning this internal tool will spend 10-15 seconds of GPU time on creative writing,
trivia, and any other off-topic request an employee sends it, correctly labeled but not refused.
Whether that's acceptable is a product decision (a general-purpose local LLM assistant may be a
feature, not a bug, for some deployments) rather than an obvious defect — flagged here because
`AUDIT_PROMPT.md` explicitly asks for 5 out-of-scope probes and this is the one of two tested
that didn't refuse.

**Conversation scope / follow-ups — tested, works correctly on the one case tried.** A 2-turn
conversation (query #9: "Công ty chi trả Số tiền bảo hiểm trong trường hợp nào theo sản phẩm An
Tâm Bảo Vệ?" → query #10, an ellipsis follow-up with no product name: "Còn nếu tử vong do tai
nạn thì sao?") correctly stayed scoped to the same product and cited the same source document
in its answer ("Công ty chi trả Số tiền bảo hiểm nếu Người được bảo hiểm tử vong do tai nạn...
[1]", same `doc_id=9b9870ac-...`). This matches `app/retrieval/conversation_scope.py`'s intended
behavior (`_scope_filter` in `app/api/chat.py:218-242`). Only one scope transition was tested in
this pass (single product, no product-switch mid-conversation, no 4-turn chain) — the fuller
4-turn pronoun/ellipsis test the prompt asks for is deferred; this one result is a positive
data point, not proof of the harder cases.

**Prompt suggestions**: tested suggestion #1 verbatim ("Phí thuần (net premium) là gì và được
tính như thế nào theo tài liệu định phí?..." from `scripts/prompt_suggestions.json`) — answered
correctly, grounded, with citations (query #6 above). The other 5 suggestions were not tested
live in this pass (time budget); given #1 passed cleanly and the corpus was purpose-built to
answer these categories (formula/notation/procedure/clause/figure — see
`.claude/skills/insurance-rag-pipeline/SKILL.md` §7), spot-testing the remaining 5 is a cheap,
high-value follow-up (each is one curl call) rather than a re-audit.

## 4.4 Answer quality spot-check

Grading the 10 live answers against grounded/partially-grounded/hallucinated/wrongly-refused,
cross-checked against `eval/golden_set.jsonl`'s expected answers where applicable:

- **Grounded, correct, cited** (7/10): queries #1, #4, #5, #6, #9, #10 all cite a real document
  and the cited section plausibly supports the claim (verified by matching the answer's claim
  against the citation's document title/section string — full chunk-text verification would
  require opening each source file, not done here). Query #4's numeric table lookup ($l_x=967625$
  at age 32) is exactly the kind of table-cell answer the skill's own notes flag as
  historically risky (`.claude/skills/insurance-rag-pipeline/SKILL.md` §"Metrics") — correct in
  this sample, but numeric-table answers are worth weighting up in any future golden-set
  additions given that history.
- **Correctly and honestly refused** (1/10): query #3 (retirement-age benefit, genuinely absent
  from the synthetic corpus) — clean refusal, matches the golden set's expected category.
  Query #7 (stock price) is arguably the same bucket (correctly refused, out-of-scope).
- **Correctly labeled general-knowledge, not hallucinated-as-fact** (2/10): queries #2 and #8 —
  both clearly disclaimed as non-company-sourced. #2 is a legitimate use of that mode; #8 is the
  scope-creep finding above.
- **Hallucinated or wrongly refused**: none observed in this sample of 10 — consistent with
  `docs/audit/roadmap.md`'s Day 7 result of `false_refusal_rate: 0.0` on the adversarial category
  and the three still-open items (`q35`, `q52`, `q59`) not being among the questions tested here.
  This sample is too small (10 items vs. the 72-item golden set) to either confirm or contradict
  the automated RAGAS trend — it corroborates rather than replaces it.

## Unverified suspicions (Phase 4)

1. **Does closing the tab / navigating away mid-stream actually free the server-side Ollama
   call?** `app/generation/generator.py`'s streaming loop has no `request.is_disconnected()`
   check. Confirm with: open `/chat/`, send a question, close the tab within ~2s, then watch
   `ollama ps` / server CPU for whether generation continues to completion anyway.
2. **Failure mid-stream (kill Ollama mid-request)**: code read suggests a graceful
   `_CONNECTION_ERROR_MESSAGE` chunk (`generator.py:478-484`), not verified live. Confirm with:
   start a query, `pkill -f ollama` (or stop the Ollama server process) 5s in, observe what the
   browser actually renders.
2. **Concurrency**: two simultaneous browser tabs / two accounts asking at once — not tested.
   Confirm with two parallel `curl` streams timed against each other; watch whether the second
   one's TTFT roughly doubles (serialized) or stays flat (parallel).
4. **The other 5 prompt suggestions** — only #1 of 6 was live-tested. Confirm the remaining 5
   with one curl call each (content field is in `scripts/prompt_suggestions.json`).
5. **Retrieval-vs-rerank-vs-generation cost breakdown** — `TimingContext` doesn't currently
   decompose end-to-end elapsed time into stages, so it's not possible to say from the logs alone
   whether reranking or query-expansion is the dominant cost without adding instrumentation
   (`docs/audit/roadmap.md`'s Day 7 numbers come from a *different* harness, `eval/run_ragas.py`'s
   direct pipeline calls, not this HTTP/SSE path, and aren't directly comparable per that
   document's own caveat).
