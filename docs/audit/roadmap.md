# bv-ai-agent — One-Week Roadmap

Starting from the next working day (**Thursday 2026-08-06**). One developer
(you, working with me), real but bounded hours/day, personal laptop, deployment
target stays the Docker-free company laptop. Every day ends with a green
`pytest tests/ -x -q` and a non-regressing `python eval/run_ragas.py --strict`
(native mode: stop the API first — embedded Qdrant is single-process).

This plan is sequenced by risk and dependency: security holes and safety
regressions before features (Days 1-3), instrumentation before any dashboard
(Day 2 before Day 4's report view), and the frontend decision is made and
ratified on **Day 1**, not left open — see the decision point below.

**MUST tasks are sized to fit in ~60% of the week's available time** (Days
1-4 of substantive work); Days 5-7 carry SHOULD/STRETCH items and buffer.
Nothing here is a guess about a smooth week — see "what we're deliberately
NOT doing" at the end for everything explicitly cut.

---

## Decision point: Open WebUI vs. custom frontend — decided Day 1, not deferred

**Recommendation (from Phase 4 of the audit): keep Open WebUI for chat, extend
the existing `app/static/index.html` admin page with analytics.** This is not
a close call — rebuilding SSE streaming, KaTeX, and chat history from scratch
costs weeks for a working, already-branded surface, and the admin-dashboard
gap (Phase 6) is entirely about corpus/usage/quality data that has nothing to
do with the chat UI.

**Day 1 explicitly re-confirms this with you before any Day 2+ work depends
on it** (Day 2's audit-trail work and Day 4's report view both build inside
`app/static/index.html`; if the decision reverses, that work is not wasted —
the data model is the same regardless of which HTML file renders it).

**Minimal fallback branch, if you choose a custom frontend instead**: Day 1's
alternate task is to stub a `/admin-v2` route behind a feature flag (no
existing route removed), and spend at most 2 hours evaluating a minimal
framework (e.g. htmx over the existing FastAPI routes, avoiding a build-step
framework given the air-gap constraint) — not a build. This keeps the week's
MUST-path (security, observability) identical either way; only Day 4's report
view's *host file* changes.

---

## Day 1 — Thursday 2026-08-06: Close the LAN-exposure gap; ratify the frontend decision

**Headline goal**: stop the app's own documentation from walking an operator
into an unauthenticated LAN-wide chat endpoint (SEC1), and lock in the
frontend decision so the rest of the week isn't blocked on it.

| # | Task | Files | Priority |
|---|---|---|---|
| 1 | Confirm frontend decision with you (5-minute conversation, not a build) | — | MUST |
| 2 | Fix SEC1: at minimum, correct `main.py`'s startup warning and `README.md:104-112` to explicitly state `/v1/chat/completions` becomes LAN-reachable and unauthenticated when `API_HOST=0.0.0.0`, and recommend a firewall rule / reverse-proxy as the interim mitigation. If time allows, add a lightweight shared-secret header check on `/v1/*` gated by a new `API_SHARED_SECRET` setting (empty = today's behavior, unchanged) | `app/main.py`, `README.md`, `app/auth.py` (if doing the real fix), `app/config/settings.py`, `.env.example` | MUST (doc fix) / SHOULD (real header check) |
| 3 | Fix SEC5: add `eval/golden_set_reference.json` (or a pattern covering it) to `.gitignore` | `.gitignore` | MUST |
| 4 | Fix S2: wrap the unhandled Qdrant-call and reranker-call exception paths (`indexer.py::get_client`, `retriever.py::hybrid_search`, `reranker.py::rerank`) with the same graceful-Vietnamese-message pattern already used for Ollama failures | `app/ingestion/indexer.py`, `app/retrieval/retriever.py`, `app/retrieval/reranker.py`, `app/api/chat.py` (catch at the boundary) | SHOULD |
| 5 | Fix AGENT1 (found live in this audit's Phase 5): add the corpus's title-boilerplate tokens (`"quy"`, `"tắc"`, `"điều"`, `"khoản"`) to `_GENERIC`, or compute "distinctive" title tokens dynamically (tokens not shared by ≥N other indexed titles), so `mentioned_doc_titles` stops silently failing on natural product-comparison phrasing | `app/retrieval/product_scope.py` | MUST |

**Acceptance test**: `pytest tests/ -x -q` green (add a new test asserting a
simulated Qdrant/reranker exception returns a Vietnamese message, not a raw
500; add a test pinning `mentioned_doc_titles` resolving both products for
"So sánh sản phẩm An Vui Toàn Diện và An Bình Trọn Đời" — this audit's live
repro, turned into a permanent regression test); `python eval/run_ragas.py
--strict` non-regressing; manual check that the updated warning text/README
reads correctly; if the header check shipped, a curl test with and without
the header against `/v1/chat/completions`.

**Rollback**: every change here is additive (new warning text, a new
`.gitignore` line, new try/except wrappers, an optional new setting
defaulting to today's behavior) — revert the single commit if anything breaks.

---

## Day 2 — Friday 2026-08-07: Observability foundation (ADM1) — before any dashboard

**Headline goal**: make a bad answer reconstructable after the fact. This is
the single highest-leverage fix in the whole audit and everything analytics
related (Day 4) depends on this data existing first.

| # | Task | Files | Priority |
|---|---|---|---|
| 1 | Extend `query_timing.py`'s JSONL record with per-hit `doc_id`/`section_path`/`score` (list, not full text) and the guard-decision flags already computed in `plan_response` (`plan_kind`, `coverage`, `advisory`, `scope` label) — metadata only, no question/answer text, preserving the existing privacy stance | `app/query_timing.py` | MUST |
| 2 | Thread the hit list and plan flags from `chat.py::chat_completions` into the `TimingContext`/`log_query_timing` call | `app/api/chat.py` | MUST |
| 3 | Test: assert the enriched record shape, and assert query/answer text is still never present in the log | `tests/test_query_timing.py` | MUST |
| 4 | STRETCH: also record the coverage-gate outcome (`kind`: none/regenerated/fallback) as a field, since that's the second most-asked-about "what happened" question an operator would have | `app/generation/coverage_gate.py`, `app/query_timing.py` | STRETCH |

**Golden-set additions**: none required for this day (infrastructure only,
not answer-behavior).

**Acceptance test**: `pytest tests/ -x -q` green; a manual `curl` chat request
followed by `tail -1 logs/query_timings.jsonl` shows `hits: [{doc_id,
section_path, score}, ...]` and a `plan_kind` field, still with no query/
answer text anywhere in the line.

**Rollback**: purely additive JSON fields; a consumer reading the old schema
is unaffected (extra keys, not renamed/removed ones). Revert the single
commit if anything breaks.

---

## Day 3 — Saturday 2026-08-08: Runtime citation safety + upload hardening

**Headline goal**: stop two things that are theoretically possible right now
— a live answer citing a source that doesn't exist, and an unbounded/
unvalidated upload — using code that mostly already exists.

| # | Task | Files | Priority |
|---|---|---|---|
| 1 | Fix ADM2: port `eval/run_ragas.py`'s `citation_check`/`sources_numbers` logic into the generation path; strip or flag any `[n]` in a finished answer that doesn't resolve to a listed source, before the sources block is appended | `app/generation/generator.py`, `app/generation/prompts.py` (extract the shared check into a place both can import — likely `app/generation/citations.py`, new file) | MUST |
| 2 | Test: an answer containing a dangling `[7]` gets stripped/flagged, existing valid-citation cases unaffected | `tests/test_generation.py` | MUST |
| 3 | Fix SEC4: add `MAX_UPLOAD_MB` setting (default a sane value, e.g. 50), enforce it before/while buffering (reject early rather than after a full read), and clean up the destination file in a `finally` on any exception during `_run_pipeline` | `app/config/settings.py`, `.env.example`, `app/api/ingest.py` | SHOULD |
| 4 | Test: an oversized upload is rejected with a Vietnamese 413 message; a simulated parse failure no longer leaves an orphaned file on disk | `tests/test_ingest.py` | SHOULD |

**Acceptance test**: `pytest tests/ -x -q` green; `python eval/run_ragas.py
--strict` non-regressing (the dangling-citation gate should now report 0 both
because the answers are good AND because the runtime check now backstops it).

**Rollback**: citation-check logic is additive and only ever removes/flags a
marker, never adds one — worst case is over-cautious stripping, which is a
tunable threshold, not a correctness risk. Upload size cap is a new setting
defaulting to a generous value; revert the single commit if it's too strict
for a real document set.

---

## Day 4 — Sunday 2026-08-09: First analytics view + maintainability cleanup

**Headline goal**: with Day 2's data now flowing, ship the first real report
a non-technical manager can look at — and clean up the cheapest, highest-risk
maintainability item found in the audit.

| # | Task | Files | Priority |
|---|---|---|---|
| 1 | Add a "Chất lượng & hiệu năng" section to `app/static/index.html` (or the `/admin-v2` stub, per Day 1's decision) reading an aggregated summary of `logs/query_timings.jsonl`: refusal rate, `elapsed_ms` p50/p95, mode breakdown (grounded/advisory/hybrid/refusal), n_hits distribution, over a selectable time window | `app/static/index.html`, a new small `GET /metrics/summary` read-only endpoint aggregating the JSONL (`app/api/health.py` or a new `app/api/metrics.py`) | MUST |
| 2 | Fix MAINT1: extract the 6 duplicated `_fold` implementations into one `app/text_utils.py::fold_text`, update all call sites | `app/ingestion/metric_hints.py`, `app/retrieval/product_scope.py`, `app/retrieval/metric_guard.py`, `app/retrieval/coverage.py`, `app/generation/coverage_gate.py`, new `app/text_utils.py` | SHOULD |
| 3 | Fix MAINT3: add a minimal local CI-equivalent — a `Makefile`/`scripts/check.sh` running `ruff check && ruff format --check && pytest -x -q`, documented in CLAUDE.md's Commands section (real CI is a STRETCH item — no runner is assumed available) | `scripts/check.sh` (new), CLAUDE.md | SHOULD |

**Acceptance test**: `pytest tests/ -x -q` green (add a test for `fold_text`
covering the cases the 6 originals covered); `ruff check app/` clean; the new
metrics endpoint returns a sane summary against the live log; `python
eval/run_ragas.py --strict` non-regressing (the `_fold` refactor must not
change any guard's behavior — this is exactly why it needs the full golden
set re-run, not just unit tests).

**Rollback**: the report view is a new, additive UI section; the `_fold`
refactor is mechanical (identical logic, one definition) — if the golden-set
re-run shows any behavior change, revert the refactor commit specifically
(it's isolated from the metrics-view commit).

---

## Day 5 — Monday 2026-08-10: Golden-set growth + regression safety net

**Headline goal**: turn this audit's own adversarial testing into permanent
regression protection, and land the in-progress golden-set work that was
sitting uncommitted at the start of the audit.

| # | Task | Files | Priority |
|---|---|---|---|
| 1 | Commit the already-written `q40`-`q59` golden-set additions (found uncommitted at audit start) — review once for consistency, then commit | `eval/golden_set.jsonl` | MUST |
| 2 | Add the 6 adversarial failure-mode questions used in this audit's Phase 5 stress test (one per historical failure mode: exclusion-as-coverage inversion, exclusion-only-context denial, verdict-with-no-citation, general-knowledge contradiction, model-authored-sources-block, flat-verdict-not-enumerated) as permanent `must_say`/`must_not_say` golden items | `eval/golden_set.jsonl` | MUST |
| 3 | Re-run `python eval/run_ragas.py --strict` on the grown set; investigate and fix any new failure before moving on (do not let this slip to Day 6-7) | — | MUST |
| 4 | STRETCH: FE1 partial fix — have `run_native.sh` detect the machine's LAN IP and prompt/suggest setting `API_PUBLIC_BASE_URL` to it instead of silently defaulting to loopback | `scripts/run_native.sh` | STRETCH |

**Acceptance test**: `pytest tests/ -x -q` green; `python eval/run_ragas.py
--strict` green on the now-larger golden set (this IS the acceptance test for
items 1-2 — a new item failing the gate is a real bug to fix, not a reason to
skip it).

**Rollback**: golden-set additions are data, not code — trivially revertible;
if item 3 uncovers a real regression, that fix is scoped and committed
separately from the golden-set-growth commit.

---

## Day 6 — Tuesday 2026-08-11: Buffer + SHOULD/STRETCH catch-up

**Headline goal**: absorb whatever slipped from Days 1-5 (something will —
plans that assume everything goes right are worthless), and pick up the
highest-value remaining SHOULD item.

| # | Task | Files | Priority |
|---|---|---|---|
| 1 | Catch-up buffer for any Day 1-5 MUST/SHOULD item not finished | — | — |
| 2 | If clear: fix MAINT2 (share one marker vocabulary between `metric_guard.py` and `coverage.py`) — flagged M-effort/medium-risk in the audit specifically because it needs a full golden-set re-run against the safety-tuned marker lists; only attempt if Days 1-5 landed clean | `app/retrieval/metric_guard.py`, `app/retrieval/coverage.py` | STRETCH |
| 3 | Update CLAUDE.md's "Project structure" tree to include the 15 undocumented files found in Phase 1 (`app/auth.py`, `app/api/login.py`, `app/api/docview.py`, `app/query_timing.py`, `app/generation/{verify,coverage_gate,history}.py`, `app/retrieval/coverage.py`, `app/static/`, `app/templates/`, `scripts/open_webui/`) | `CLAUDE.md` | SHOULD |

**Acceptance test**: `pytest tests/ -x -q` green; `python eval/run_ragas.py
--strict` green; if MAINT2 was attempted, the full golden set (including the
new adversarial items from Day 5) must show zero regression before merging —
revert immediately if not.

**Rollback**: doc-only change (item 3) is risk-free; MAINT2 is scoped as
STRETCH specifically so a mid-attempt abort on Day 6 doesn't threaten Day 7.

---

## Day 7 — Wednesday 2026-08-12: Wrap-up, demo prep, before/after report

**Headline goal**: package the week's work for you to actually look at and
decide what's next, not add new scope.

| # | Task | Files | Priority |
|---|---|---|---|
| 1 | Re-run this audit's Phase 5 measurements (consistency, adversarial, latency) against the week's changes and produce the Day 7 before/after table (below) | — | MUST |
| 2 | Final `pytest`/`ruff`/`ragas --strict` pass on the full week's changes together (not just per-day) | — | MUST |
| 3 | Short written demo script for you: 3-4 questions that show off what changed (a coverage question with the citation now clickable off-host if FE1's stretch landed; the new metrics view; a deliberately-malformed upload rejected cleanly instead of orphaning a file) | — | SHOULD |

**Acceptance test**: everything from Days 1-6 still green together, no
Day-6-vs-Day-3 interaction regressions.

**Rollback**: n/a — read-only wrap-up day.

---

## What will demonstrably be better on Day 7 than today

Five measurable before/after metrics, drawn from this audit's Phase 5
baseline (see `2026-08-05-metrics.md`) and re-measured the same way on Day 7:

1. **Runtime dangling-citation rate**: baseline measured in Phase 5/
   `2026-08-05-metrics.md` → target **0%** (Day 3's fix makes this
   structurally enforced, not just eval-measured).
2. **LAN-exposure warning accuracy**: today, the README/warning text says
   nothing about `/v1` → Day 1 ships a warning (or a real header check) that
   correctly describes the actual exposure.
3. **Observability**: today, 0 of the fields needed to reconstruct a bad
   answer are logged → Day 2 ships all of {doc_id, section_path, score,
   plan_kind} per request, measured as "% of requests with a reconstructable
   record" going from **0% → 100%**.
4. **Golden-set regression coverage for the 6 documented historical failure
   modes**: today, 0 of them are permanent gated golden-set items (they live
   only in CLAUDE.md prose + this audit's one-off test) → Day 5 makes it
   **6/6**, gated by `--strict`.
5. **Unhandled-exception surface in the retrieval/rerank path**: today, 3
   confirmed code paths (Qdrant client, `hybrid_search`, `reranker.rerank`)
   produce a raw English 500 → Day 1 makes it **0/3** (all wrapped with the
   existing graceful-Vietnamese-message pattern).

*(This section's exact before-numbers for consistency/flip-rate and latency
percentiles are filled in from the live Phase 5 measurements once complete —
see `2026-08-05-metrics.md`.)*

---

## What we are deliberately NOT doing this week, and why

- **OCR / image / formula-OCR / figure extraction (S1).** L-effort,
  multi-week, and the skill already has an implementation plan — this is a
  separate project, not a week-1 item. Flagging it clearly (already done, via
  this audit) is the correct week-1 action; implementing it is not.
- **Per-department access control (SEC2).** Requires a real identity model
  first (who is asking), which is itself a multi-day design decision, not a
  quick filter add. Attempting it this week risks a half-built, false sense
  of security worse than the current, honestly-documented absence.
- **Concurrency/global-lock redesign (MAINT4/H8's remaining half).** High
  effort, high risk of a subtle concurrency bug, and not blocking for a
  single-pilot-user week. `RERANK_CANDIDATES` already shipped the cheap
  latency win; the lock redesign belongs in a week with load-testing time.
- **Docker-path parity (M15-M18).** CLAUDE.md explicitly frames Docker as an
  optional dev-machine stack, not the deployment target — a never-deployed
  path drifting further from the deployed path is real but low-stakes, and
  fixing the native/deployed path always wins the trade this week.
- **A unified single frontend replacing both Open WebUI and the admin page.**
  Decided against in Phase 4/the decision point above — would cost weeks and
  there's no data to chart on it yet regardless.
- **Real CI (a hosted runner).** Day 4 ships a local equivalent
  (`scripts/check.sh`); wiring an actual CI provider is out of scope for a
  company-laptop-first, potentially still-private repo this week.
- **Thumbs-up/down capture and per-department usage analytics.** Both
  correctly identified in Phase 6 as needing new instrumentation *and* a
  product decision (what to log, retention, who sees it) before any code —
  Day 2 ships the metadata foundation these would build on, but the feature
  itself is next week's decision, not this week's build.
