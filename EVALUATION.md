# EVALUATION — BV AI Agent (Local RAG Assistant)

**Date:** 2026-07-24 · **Branch:** `main` @ `55b37ac` (+ uncommitted work)
**Evaluator environment:** macOS 24.6.0, Apple M1 Pro, 16 GB RAM, native (no-Docker) stack running,
`CHAT_MODEL=qwen3:8b` on Metal, embedded Qdrant, 123 indexed chunks across 10 documents.

> **Scope note:** this is an assessment only — **no application code was modified**.
> All findings below were reproduced against the running system or by calling the
> project's own pure functions. Per `CLAUDE.md` rule 2, no real document titles,
> content, or figures appear in this file; real pilot documents are referred to
> only by count.

---

## 0. Executive summary

The project is **substantially more mature than a prototype**. The architecture is clean and
genuinely layered, the security/air-gap posture is excellent, the Vietnamese prompt engineering
is thoughtful, and several hard RAG problems (exclusion polarity, wrong-product answers, metric
remapping, deterministic disclaimers) are solved with real engineering rather than prompt wishes.
Live testing confirmed correct exclusion handling, correct wrong-product refusal, working
cross-lingual (EN→VI) retrieval, correct LaTeX, and a working citation/sources block.

Three things block a confident pilot:

1. **A safety guard added after the last evaluation run now hard-refuses ordinary questions.**
   The product-scope guard treats any non-stopword after "bảo hiểm/sản phẩm/hợp đồng" as a
   product name and refuses when that word is absent from retrieved titles. It refuses
   **3 of the project's own 33 golden-set questions** and **2 of the 6 prompt suggestions shipped
   in the branded UI** — regardless of how good retrieval was.
2. **Latency is not yet usable for interactive work.** Measured end-to-end: 43 s – 95 s per
   question single-user (one outlier at 504 s under concurrent ingest). Reranking alone measured
   30 s – 164 s. A process-wide lock serializes all users.
3. **The evaluation harness cannot see any of this.** `eval/run_ragas.py` exercises
   search → rerank only; it does not run the spellcheck gate, query rewrite, conversation scope,
   product-scope guard, or advisory routing. Its stored `false_refusal_rate: 0.0` measures a code
   path users never reach, and its last run (2026-07-12) predates all of these features and used
   a different model (`qwen3:1.7b`).

None of the three is architecturally deep. Items 1 and 3 are days of work; item 2 is the one real
engineering project.

---

## 1. Run & verify

### 1.1 Native (pip) mode — **works**

The stack was already running via `scripts/run_native.sh` and was healthy:

```
GET /health  → {"status":"ok","services":{"ollama":{"status":"up","http_status":200},
                                          "qdrant":{"status":"up","mode":"embedded"}}}
GET /v1/models → {"id":"bao-viet-life","name":"Trợ lý AI Bảo Việt Life"}
```

All four warmup steps succeeded (`logs/api.log`): Qdrant collection, bge-m3 embedder,
bge-reranker-v2-m3, Ollama chat model. Open WebUI serving on `:3000`, admin UI on `:8000`.

Service-to-service communication verified end to end: Open WebUI → FastAPI `/v1/chat/completions`
→ Ollama `/api/chat` + embedded Qdrant → back with SSE. Ollama reports `qwen3:8b` at `100% GPU`.

**Undocumented / rough edges found in the native path**

| Observation | Detail |
|---|---|
| `.venv` runs **Python 3.10.11** | README and `scripts/setup_native.sh:6,20` state 3.11/3.12. The app venv works on 3.10; only `.venv-webui` (3.12) actually needs ≥3.11. The stated requirement is stricter than reality — harmless but misleading during handover. |
| `qdrant_storage/` holds **two** stores | `collections/` + `raft_state.json` (11 MB, stale Docker server-mode) alongside `local/` (1.7 MB, the live embedded store). Nothing cleans up the old one; a confused operator could point at the wrong one. |
| `ADMIN_PASSWORD` breaks `pytest` | Following the README instruction to set it makes 7 tests fail (see §2.9). |
| Ingest is slow enough to look hung | A single synthetic PDF took **124.5 s in Docling alone** before chunking/enrichment. The admin UI does warn ("có thể mất một lúc"), but there is no progress indication. |

### 1.2 Docker Compose mode — **config valid, cannot be launched alongside native**

- `docker compose config` → **OK**; all image tags pinned (`ollama:0.9.6`, `qdrant:v1.12.4`,
  `open-webui:0.5.4`). No `:latest` anywhere. Good.
- Started the `qdrant` service in isolation to verify image + volume wiring:
  `healthz check passed`, `collections` endpoint served the existing `insurance_docs` collection
  from the host-mounted `./qdrant_storage`. Container then removed.
- **Port collision, undocumented:** with the native stack running, 3 of the 4 compose ports are
  already bound (`11434`, `8000`, `3000`; only `6333` is free). `docker compose up -d` fails on a
  machine that has ever run `run_native.sh` without first running `stop_native.sh`. The README
  presents the two paths side by side with no warning.
- A **full `api` image build was not attempted** — it pulls `python:3.12-slim`, torch/torchvision
  from the PyTorch CPU index, FlagEmbedding and Docling (multi-GB, long). The pinned versions
  (`torch==2.12.1`, `torchvision==0.27.1`, `docling==2.112.0`, `FlagEmbedding==1.3.5`,
  `transformers==4.57.6`) match exactly what is installed and working in the native `.venv`, so
  the pin set is internally consistent.
- **`Dockerfile` does not `COPY scripts/`** ([Dockerfile:57-59](Dockerfile#L57-L59) copies only
  `app/` and `eval/`). `docker compose exec api python scripts/ingest_knowledge_pack.py` — a
  documented command — cannot work in the container.

### 1.3 Ingestion pipeline end-to-end — **works for MD / XLSX / PDF / glossary; images not implemented**

Ran every synthetic document through the live `POST /ingest`:

| File | Format | Wall time | Chunks |
|---|---|---|---|
| `cong_thuc_nien_kim_bang_ty_le_tu_vong.md` | Markdown + LaTeX | 471.3 s\* | 3 |
| `danh_sach_chi_tra_quyen_loi_q1_2025.xlsx` | Spreadsheet | 19.0 s | 2 |
| `huong_dan_du_phong_toan_hoc.md` | Markdown + LaTeX | 27.9 s | 3 |
| `huong_dan_tham_dinh_so_bo.pdf` | PDF (Docling) | 124.5 s in Docling alone | 1 |

\* first run, cold Docling/LLM path and contended with a concurrent query batch; the second
formula-heavy Markdown file at 27.9 s is the representative figure.

`.png/.jpg/.jpeg` are routed to `NotImplementedError`
([router.py:62-63](app/ingestion/router.py#L62-L63)) — image ingestion, formula OCR and figure
extraction are **empty stub files** (§2.2).

### 1.4 Retrieval & answer quality — live queries

| Question | Latency | Verdict |
|---|---|---|
| "Phí thuần (net premium) được tính như thế nào?" | 75.4 s | ✅ correct formula + LaTeX |
| "Quy trình giải quyết quyền lợi bảo hiểm gồm những bước nào?" | 43.5 s | ❌ **false refusal** — document is indexed, retrieval scored 0.983, guard discarded it |
| "Thủ đô của nước Pháp là gì?" | 79.6 s | ✅ hybrid fallback, correctly labeled with `HYBRID_DISCLAIMER` |
| "Sản phẩm \<absent product\> có quyền lợi tử vong bao nhiêu?" | 82.5 s | ✅ correct refusal (guard working as intended) |
| "Trượt tuyết có được chi trả không?" | 95.0 s | ✅ **exclusion polarity correct** — concluded NOT covered, with citations |
| "What is the mathematical reserve formula?" (EN) | 504.1 s\* | ✅ correct VI answer + LaTeX + calc disclaimer + sources; EN→VI bridging works |

\* run concurrently with ingestion; not representative of single-user latency.

**Quality is good where retrieval succeeds.** The failure mode is not hallucination — it is
false refusal and latency.

---

## 2. Backend assessment

### Summary table

| # | Area | Rating | Strengths | Weaknesses |
|---|---|---|---|---|
| 2.1 | Architecture & maintainability | **8.5/10** | Clean layering; every tunable through `settings.py`; pure, injectable functions; excellent docstrings that explain *why* | Guard modules accreting as parallel special cases; `chat.py::_retrieve` growing branchy; 3 dead settings |
| 2.2 | Document parsing | **6/10** | Docling + pypdfium2 fixes VN diacritics; pandoc keeps OMML→LaTeX; XLSX→Markdown with header repeat; NFC everywhere | OCR/image/formula-OCR/figure extraction are **empty stubs**; `page` never populated by any parser; 124 s/PDF |
| 2.3 | Chunking | **4/10** | Equation and table binding logic is correct and well-tested; caption-binds tables | **Only 7 % of chunks reach the configured 500–800 token target**; `CHUNK_MIN_TOKENS` is dead config; no cross-section merge |
| 2.4 | Embeddings & Qdrant | **7.5/10** | Real hybrid dense+sparse from one bge-m3 pass; explicit RRF; idempotent upsert; deterministic point IDs | No payload indexes; `list_documents()` scrolls the whole collection and is called per comparison query; embedded mode is single-process |
| 2.5 | Prompting & RAG orchestration | **8/10** | Shared rule blocks prevent divergence; disclaimers enforced in **code** not prompt; refusal is deterministic; sources block always accurate | Inline citation format drifts from the numbered block; `num_ctx` never sent so context silently truncates at 4096 |
| 2.6 | FastAPI | **7.5/10** | Proper SSE, threadpool offload, lifespan warmup, per-stage timing logs, `_safe_filename` traversal guard, good error mapping | Unbounded upload read into memory; no MIME validation; no request timeout/queue; no structured logging |
| 2.7 | Security & on-prem integrity | **9/10** | **Zero external network calls verified**; `.gitignore` careful and well-reasoned; `data/real/` empty and untouched; httponly/samesite cookie; constant-time compare; no telemetry | Weak default admin password in the working `.env`; no login rate limit; citation base URL unusable off-host |
| 2.8 | Performance | **3.5/10** | Warmup, `keep_alive`, `think:false` are all correct and material wins | 43–95 s/query; rerank 30–164 s; global locks serialize every user; API process ~10 GB RSS on a 16 GB box |
| 2.9 | Testing & evaluation | **5.5/10** | 266 tests, fast (2 s), no services needed; thoughtful golden set (33 Q, 7 categories); custom offline eval harness avoiding cloud judges | **7 tests fail** in the documented deployment config; eval **does not exercise any query-time guard**; baseline is 12 days stale and from a different model |

### 2.1 Architecture, layering, maintainability — 8.5/10

**Pros.** The `parse → clean → chunk → enrich → index` / `rewrite → expand → search → rerank →
generate` split is real, not nominal. Heavy imports are consistently lazy
([indexer.py:41-46](app/ingestion/indexer.py#L41-L46),
[reranker.py:32-38](app/retrieval/reranker.py#L32-L38),
[main.py:44-47](app/main.py#L44-L47)) so `pytest` runs in 2 s with no model loads. Config
discipline is near-perfect: `grep` found no `os.getenv()` outside `settings.py`. Guard modules are
pure functions with injectable dependencies, which is why I could reproduce two production bugs by
calling them directly with no services running — that testability is a genuine asset.

**Cons.** The retrieval layer has grown seven sibling guard modules (`spellcheck`,
`product_scope`, `metric_guard`, `conversation_scope`, `comparison`, `query_rewrite`,
`query_expansion`), each added for one observed failure, each with its own feature flag. They
compose in `chat.py::_retrieve` ([chat.py:162-254](app/api/chat.py#L162-L254)) as nested
conditionals with no shared contract, and interactions between them are neither tested nor
evaluated. This is exactly how the §3.1 bug survived. Three settings are declared, documented in
`.env.example`, and **never read**: `llm_context_window`, `chunk_min_tokens`, and the
vision/OCR trio (`vision_model`, `embed_model`, `ocr_language`).

### 2.2 Document parsing — 6/10

**Pros.** The `PDF_BACKEND=pypdfium2` default ([settings.py:202-207](app/config/settings.py#L202-L207))
documents and fixes a real Vietnamese diacritic corruption in professionally typeset PDFs — that is
hard-won knowledge, correctly captured. DOCX goes through pandoc (`gfm+tex_math_dollars`), never
`python-docx`, so OMML equations survive as LaTeX. Docling runs with `do_formula_enrichment` and
offline artifacts, with a correct guard against docling's own `DOCLING_ARTIFACTS_PATH` hard-fail
([settings.py:210-214](app/config/settings.py#L210-L214)). Scanned PDFs raise a clear, actionable
error rather than silently indexing empty text ([pdf_parser.py:90-96](app/ingestion/parsers/pdf_parser.py#L90-L96)).
The title-derivation logic that merges a generic heading with a more complete filename
([markdown.py:67-89](app/ingestion/parsers/markdown.py#L67-L89)) is a smart, well-documented fix.

**Cons.**
- **Images, OCR, formula-OCR and figure extraction do not exist.** All four files are docstring +
  `TODO` only: [ocr.py](app/ingestion/parsers/ocr.py),
  [image_parser.py](app/ingestion/parsers/image_parser.py),
  [formula_ocr.py](app/ingestion/parsers/formula_ocr.py),
  [figure_extract.py](app/ingestion/parsers/figure_extract.py). `CLAUDE.md` opens by listing
  "images (scans, screenshots)" as an input and charts as handled content; the README is honest
  about this under "Next", but the top-of-file claims are not.
- **No parser populates `page`.** `ParsedSection.page` defaults to `None`
  ([schemas.py:60-69](app/models/schemas.py#L60-L69)) and nothing sets it — verified across all
  123 indexed chunks (`page` is `None` for 100 %). Consequences in §3.5.
- Actuarial pre-subscript cross-checking against the glossary and `needs_review` tagging (skill
  §1) are specified but not implemented; `needs_review` is always `False`.

### 2.3 Chunking — 4/10 (largest quality lever)

**Pros.** The equation-unit and table-unit binding is genuinely correct: a display equation is
merged with its preceding paragraph and following "trong đó:" list
([chunking.py:72-103](app/ingestion/chunking.py#L72-L103)); a table is merged with its caption
([chunking.py:106-123](app/ingestion/chunking.py#L106-L123)); oversized tables split by row groups
with the header **and caption** repeated ([chunking.py:140-167](app/ingestion/chunking.py#L140-L167)).
Because blocks are atomic, inline `$...$` can never be split. Token counting is injectable and the
indexer passes the real bge-m3 tokenizer. This part is well designed and well tested.

**Cons — measured on the live index (123 chunks):**

| Approx. tokens | Chunks | Share |
|---|---|---|
| < 100 | 67 | **54 %** |
| 100–299 | 42 | 34 % |
| 300–499 | 5 | 4 % |
| **500–800 (configured target)** | **8** | **7 %** |
| > 800 (oversize) | 1 | 1 % |

Median chunk ≈ **78 tokens**; minimum 4 tokens (a 12-character chunk is indexed). Only 9/123 reach
`CHUNK_MIN_TOKENS=500`.

Root cause: `chunk_document` packs **within one section only**
([chunking.py:250-252](app/ingestion/chunking.py#L250-L252)) and the sectionizer emits one section
per heading at any depth ([markdown.py:146-160](app/ingestion/parsers/markdown.py#L146-L160)). A
policy with deep `Điều/Khoản/Điểm` nesting therefore yields dozens of one-sentence chunks. There is
no merge step, and `settings.chunk_min_tokens` is never passed to the chunker
([ingest.py:162-168](app/api/ingest.py#L162-L168) passes only `max_tokens` and `overlap_pct`).

This is why retrieved chunks contain dangling references ("các thương tật trong Danh sách trên" with
no list in the chunk), and it forces the reranker to discriminate between many near-identical
fragments — which is both a quality and a latency cost.

### 2.4 Embeddings & Qdrant — 7.5/10

**Pros.** One bge-m3 pass yields dense + sparse together ([indexer.py:84-97](app/ingestion/indexer.py#L84-L97)) —
efficient and correct. RRF is computed in Python precisely so the constant is configurable and
unit-testable ([retriever.py:25-36](app/retrieval/retriever.py#L25-L36)) — a well-justified
deviation from Qdrant's built-in fusion. Ingestion is idempotent via `uuid5(doc_id, chunk_index)`
+ delete-then-upsert. The payload matches `CLAUDE.md`. Metadata filtering supports both exact and
`MatchAny` ([retriever.py:39-56](app/retrieval/retriever.py#L39-L56)), which the comparison path
uses to give each product its own full candidate pool — a good design.

**Cons.**
- **No payload indexes.** `ensure_collection` ([indexer.py:100-115](app/ingestion/indexer.py#L100-L115))
  creates vectors only. Every `doc_id` filter, count, and scroll is a full scan. Fine at 123
  points, linear at 100 k.
- **`list_documents()` scrolls the entire collection** ([indexer.py:330-365](app/ingestion/indexer.py#L330-L365))
  and is called on every comparison query via `_load_indexed_docs`
  ([comparison.py:87-94](app/retrieval/comparison.py#L87-L94)) and every product-scope check via
  `_load_indexed_titles` ([product_scope.py:393-400](app/retrieval/product_scope.py#L393-L400)).
  No caching.
- Embedded mode is single-process by design; the README documents the "stop the API before eval"
  workaround, but this makes *any* concurrent maintenance impossible and is a real operational tax.
- `DENSE_VECTOR_SIZE`/`DENSE_DISTANCE` are settings but a mismatch with the actual model would only
  surface at upsert time.

### 2.5 Prompting & RAG orchestration — 8/10

**Pros.** This is the strongest part of the project.
- `system_prompt()` composes strict/advisory from **shared blocks**
  ([prompts.py:239-262](app/generation/prompts.py#L239-L262)), so rules 2 and 4–7 cannot diverge
  between modes — the invariant `CLAUDE.md` demands is enforced structurally, not by discipline.
- Exclusion rule 6 covers **both** directions — never invert polarity, and never over-apply
  ([prompts.py:168-191](app/generation/prompts.py#L168-L191)). Live-verified correct.
- Every disclaimer is **enforced in code**, not trusted to the model:
  `_disclaimer_suffix`, `_hybrid_disclaimer_suffix`, `_advisory_disclaimer_suffix`,
  `_general_knowledge_suffix` ([generator.py:221-278](app/generation/generator.py#L221-L278)).
  `_needs_calc_disclaimer` is nicely precise — it triggers on numbers inside math spans, not on
  quoted document figures ([generator.py:202-218](app/generation/generator.py#L202-L218)).
- Zero-retrieval behaviour is deterministic, not delegated to the LLM
  ([chat.py:312-328](app/api/chat.py#L312-L328)), with a separate weaker `HYBRID_SYSTEM_PROMPT`
  that never dilutes the grounded one.
- `ThinkStripper` correctly handles `<think>` tags split across SSE deltas
  ([generator.py:69-111](app/generation/generator.py#L69-L111)).
- Open WebUI meta-tasks (title/tag generation) bypass RAG entirely
  ([chat.py:76-84](app/api/chat.py#L76-L84)) — without this every chat title would be the refusal
  sentence. Good catch.

**Cons.**
- **`num_ctx` is never sent to Ollama.** `_ollama_payload`
  ([generator.py:157-169](app/generation/generator.py#L157-L169)) sets only `temperature` and
  `num_predict`. `settings.llm_context_window = 8192` is dead. `ollama ps` confirms the model runs
  at **`CONTEXT 4096`**. With 5 chunks + system prompt (~1 200 tokens) + 6 history turns, long
  contexts are silently truncated by Ollama's context shift — a *silent* grounding failure.
- Inline citations (`[Tên tài liệu, mục X]`) and the appended numbered block (`[1] …`) use
  different schemes; the model sometimes emits `[2]`, sometimes the title form. Observed live.
- `_MAX_HISTORY_TURNS = 6` is hardcoded ([generator.py:40](app/generation/generator.py#L40)),
  contrary to the "all tunables in settings" rule.

### 2.6 FastAPI — 7.5/10

**Pros.** OpenAI-compatible SSE is correct and Open WebUI works unmodified. All blocking work is
pushed off the event loop via `run_in_threadpool`. Lifespan warmup is best-effort per step and can
never break startup ([main.py:34-62](app/main.py#L34-L62)). Per-stage latency logging
([chat.py:241-253](app/api/chat.py#L241-L253)) is what made this evaluation's latency attribution
possible — genuinely good operational thinking. `_safe_filename`
([ingest.py:97-108](app/api/ingest.py#L97-L108)) correctly blocks path traversal. The auth
middleware's public-path regex is deliberately narrow and well-commented
([auth.py:44-49](app/auth.py#L44-L49)). Error mapping (415/400/404/401) is consistent and messages
are in Vietnamese.

**Cons.**
- `dest.write_bytes(await file.read())` ([ingest.py:201](app/api/ingest.py#L201)) reads the entire
  upload into memory with **no size cap and no MIME check** — a 500 MB PDF is a 500 MB allocation.
- No request timeout or concurrency limit on `/v1/chat/completions`; with 30–160 s reranks, a
  handful of users queue unboundedly behind the global lock.
- Logging is `logging.basicConfig` with plain strings — no request IDs, no structured fields, so
  interleaved concurrent requests cannot be untangled in `logs/api.log`.
- `PATCH /documents/{id}` with a title change triggers a **full synchronous re-ingest**
  ([ingest.py:362-371](app/api/ingest.py#L362-L371)) inside the request — minutes for a PDF, with
  no progress or timeout.

### 2.7 Security & on-premise integrity — 9/10

**Pros — verified, not assumed.**
- **No data leaves the machine.** Every outbound call in `app/` targets `settings.ollama_base_url`
  (enrichment, query rewrite, generation ×3). No web search, no telemetry, no analytics, no CDN
  asset in the admin UI. `urllib` appears only as `urllib.parse.quote`.
- **`data/real/` is empty and was never read.** `.gitignore` is careful and correctly reasoned —
  including the anchored `/models/` comment explaining why unanchored `models/` would silently drop
  `app/models/`. `git ls-files` confirms no `.env`, no `data/`, no `qdrant_storage`, no
  `.webui_secret_key` is tracked; only `.env.example`.
- Knowledge-pack `source_url` is validated to `http(s)` before being rendered as a Markdown link
  ([ingest.py:72-94](app/api/ingest.py#L72-L94)) — correctly identified as an injection vector, and
  the URL is never fetched.
- Admin gate: HMAC-signed expiring cookie keyed on the password itself, `hmac.compare_digest`,
  `httponly` + `samesite=lax` ([auth.py](app/auth.py), [login.py:36-42](app/api/login.py#L36-L42)).
  Startup logs a warning when the gate is disabled ([main.py:69-73](app/main.py#L69-L73)).
- RBAC layering is sound: API on `127.0.0.1`, Open WebUI with `WEBUI_AUTH=true` on `:3000`.

**Cons.**
- The working `.env` has `ADMIN_PASSWORD=Admin123!` — trivially guessable. `.env.example` says
  "Nothing here is a secret by design", which undersells this one field.
- No rate limiting or lockout on `POST /login` — mitigated by loopback binding, but cheap to add.
- `/documents/{id}/view` and `/file` are intentionally unauthenticated so employees can click
  citations — but see §3.9: from any machine other than the server they are unreachable anyway.

### 2.8 Performance — 3.5/10

**Measured, single user, M1 Pro / Metal, `qwen3:8b`, `LLM_THINKING=false`:**

| Stage | Measured range | Source |
|---|---|---|
| Query rewrite (LLM) | 0 – 2 946 ms | `logs/api.log` |
| Glossary expansion | 1 – 3 ms | " |
| Hybrid search (bge-m3 query embed + 2× Qdrant) | 13 059 – 14 806 ms | " |
| **Rerank (bge-reranker-v2-m3, CPU)** | **30 242 – 164 280 ms** | " |
| Metric guard | 5 – 61 ms | " |
| Generation (first token) | 10 545 – 19 226 ms | " |
| Generation (total) | 15 267 – 33 297 ms | " |
| **End-to-end** | **43.5 – 95.0 s** | live queries |

**Memory:** API process ≈ **10 GB** (bge-m3 + reranker + embedded Qdrant + FastAPI) plus Ollama
**5.6 GB** for `qwen3:8b` — ≈ 15.6 GB on a **16 GB** machine. There is no headroom, and
`CLAUDE.md` says target hardware "varies".

**Cons.**
- Reranking is 60–80 % of retrieval time. Its cost is driven by candidate count (up to 40 pairs
  after RRF) × the tiny-chunk problem (§2.3) — more, smaller chunks means more cross-encoder pairs.
- **Global locks serialize every user.** `_score_lock` ([reranker.py:26](app/retrieval/reranker.py#L26))
  and `_embed_lock` ([indexer.py:37](app/ingestion/indexer.py#L37)) are process-wide. They are
  *correct* — the Rust tokenizers genuinely are not thread-safe — but the consequence is that with
  a 30–160 s critical section, a second employee's question waits behind the first, and an ingest
  blocks all chat. Throughput is ~1 query/minute regardless of thread count.
- The comparison path multiplies this: one rerank pass **per named product**
  ([comparison.py:152-169](app/retrieval/comparison.py#L152-L169)) — measured **164 s** for a
  3-product query, most of it spent on two garbage products (§3.6).
- Ingestion calls the LLM once per math chunk, sequentially, with no batching
  ([enrichment.py:86-95](app/ingestion/enrichment.py#L86-L95)).

**Pros.** `WARMUP_ON_STARTUP`, `OLLAMA_KEEP_ALIVE=2h` and `think:false` are all correct and
individually worth tens of seconds; the README's measured note (440 s Docker-CPU → 56 s native
Metal) shows the right instinct was already applied once.

### 2.9 Testing & evaluation — 5.5/10

**Pros.** 266 tests running in **2.04 s** with no services — the lazy-import discipline pays off
directly. Coverage is broad (parsers, chunking, equation-splitting, enrichment, retrieval,
spellcheck, advisory, auth, docview, knowledge pack, startup, config). The golden set is
thoughtfully categorised (33 questions: `policy_qa` 9, `formula` 7, `table_lookup` 5, `definition`
5, `notation` 4, `refusal` 2, `calculation` 1) and includes 5 English questions to test glossary
bridging. `run_ragas.py` deliberately avoids the real `ragas` package to stay offline and
dependency-free — correct call, well justified in its docstring. `ruff check` passes clean.

**Cons.**
- **7 tests fail on a correctly-deployed machine.** `Settings` reads the real `.env`
  ([settings.py:29-34](app/config/settings.py#L29-L34)), so setting `ADMIN_PASSWORD` — which the
  README instructs the deployer to do — makes the auth middleware return 401 to `TestClient`:
  ```
  FAILED tests/test_config.py::test_admin_ui_served_at_root_without_shadowing_api_routes
  FAILED tests/test_ingest.py::test_delete_document_removes_and_reports_chunks
  FAILED tests/test_ingest.py::test_delete_unknown_document_is_404_and_deletes_nothing
  FAILED tests/test_ingest.py::test_patch_metadata_only_updates_type_and_department
  FAILED tests/test_ingest.py::test_patch_rename_reingests_from_source
  FAILED tests/test_ingest.py::test_patch_unknown_document_is_404
  FAILED tests/test_ingest.py::test_patch_invalid_department_is_400
  7 failed, 259 passed in 2.04s
  ```
  Tests are environment-dependent — the "green suite" is an artifact of the dev box.
- **The eval harness exercises none of the query-time guards.** Checked every module:
  `product_scope`, `query_names_absent_product`, `advisory`, `spellcheck`,
  `maybe_suggest_correction`, `conversation_scope`, `active_scope`, `rewrite_standalone` — **none**
  appear in `eval/run_ragas.py`, whose docstring nonetheless claims it "mirrors
  `app.api.chat._retrieve`". It therefore structurally cannot detect §3.1.
- **The stored baseline is stale and not comparable.** `eval/results/run-20260712-165020.json` is
  from 2026-07-12 with `chat_model: qwen3:1.7b`, i.e. before advisory mode, the knowledge pack,
  comparison retrieval, spellcheck and the product-scope guard existed.
- That baseline also shows **`citation_rate: 0.10`** — only 10 % of answers carried an inline
  citation (0 % for `formula` and `notation`). This is a headline rule-compliance miss that the
  README's "citation compliance" claim glosses over; the appended sources block partly compensates
  but is not the same thing.
- `ruff format --check` flags 2 files: `app/ingestion/parsers/markdown.py`,
  `app/retrieval/product_scope.py`.
- No CI configuration anywhere in the repo.

---

## 3. Ranked issue list

### 🔴 Critical

**C1 — Product-scope guard hard-refuses ordinary answerable questions**
`app/retrieval/product_scope.py:403-418` (`query_names_absent_product`), invoked at
`app/api/chat.py:291-303`.

`_product_spans` ([product_scope.py:213-249](app/retrieval/product_scope.py#L213-L249)) takes any
token after a cue phrase (`bảo hiểm`, `sản phẩm`, `hợp đồng`, `chương trình`, `gói`) that is not in
the hand-maintained ~80-word `_GENERIC` stoplist and treats it as a **product name**. If that word
does not appear in any retrieved title, the endpoint returns the refusal regardless of retrieval
quality. The stoplist approach is default-deny over an unbounded vocabulary.

Reproduced (pure function, no services):

| Question | Extracted "product" | Result |
|---|---|---|
| "Quy trình giải quyết quyền lợi bảo hiểm gồm những bước nào?" | `bước` (= *step*) | **REFUSE** |
| "Hồ sơ yêu cầu bảo hiểm cần những giấy tờ gì?" | `giấy tờ` (= *documents*) | **REFUSE** |
| "Thời gian chờ của hợp đồng bảo hiểm là bao lâu?" | `lâu` (= *long*) | **REFUSE** |

Blast radius:
- **3 of the project's own 33 golden-set questions** (`q05`, `q09`, `q15`) refuse *even if every
  indexed document were retrieved* — including two `formula` questions where the "product" extracted
  was the LaTeX token `a_x`.
- **2 of the 6 prompt suggestions shipped in the branded Open WebUI** (`prompt_suggestions.json`
  entries 4 and 5) refuse. A new employee's first click returns "Tôi không tìm thấy thông tin trong
  tài liệu."
- Live confirmation: retrieval scored a **0.983** top hit and returned 5 hits; the guard discarded
  all of them (`logs/api.log`: `product-scope guard: named product absent from 5 retrieved doc(s); refusing`).

Note the specific defect: `named_product_labels` **does** resolve that same query to the correct
indexed title via `mentioned_doc_titles`, but `query_names_absent_product` ignores that
title-resolution path entirely and uses only raw cue spans.

**C2 — Test suite fails when the deployment guide is followed**
`app/config/settings.py:29-34` + `app/main.py:95-110`. See §2.9. Setting `ADMIN_PASSWORD` as the
README instructs turns 7 passing tests into 401s. Any CI or handover verification will report a red
suite for a correctly-configured machine.

**C3 — `LLM_CONTEXT_WINDOW` is dead; context silently truncates at 4096**
`app/config/settings.py:84` declared; `app/generation/generator.py:157-169` never sends `num_ctx`.
`ollama ps` shows `CONTEXT 4096` while `.env` says `8192`. System prompt (~1 200 tokens) + 5 chunks
+ 6 history turns exceeds 4096 on realistic policy questions; Ollama then silently context-shifts,
dropping grounding text without any error. This is the most dangerous kind of failure for a RAG
system — invisible.

### 🟠 High

**H4 — Chunks are ~6× smaller than configured; `CHUNK_MIN_TOKENS` unused**
`app/ingestion/chunking.py:232-270`, `app/api/ingest.py:162-168`, `app/config/settings.py:195`.
Median 78 tokens; 54 % under 100; only 7 % in the 500–800 target (§2.3). Directly degrades
retrievability, produces chunks with dangling references, and inflates rerank cost.

**H5 — `page` is never populated → PDF citation deep-links are dead code**
No parser sets `ParsedSection.page` (`app/ingestion/parsers/pdf_parser.py:83-109`,
`markdown.py:140-143`); confirmed `None` on 100 % of 123 indexed chunks. The `#page=N` deep-link
and `(trang N)` label in `app/generation/prompts.py:384-399` can never fire. Clicking a citation on
a 60-page policy booklet opens page 1.

**H6 — Comparison product extraction produces garbage labels and burns minutes**
`app/retrieval/product_scope.py:213-249` → `app/retrieval/comparison.py:142-169`.
From `logs/api.log`, one query yielded the "products"
`['<real product>', 'tren thi truong ngoai tuong', 'không']` — the Vietnamese word *không* ("no")
and a sentence fragment each triggered a **full scoped search + rerank pass**. Total rerank for that
turn: **164 280 ms**. `COMPARISON_MAX_PRODUCTS=3` caps the damage at 3× rather than preventing it.

**H7 — Evaluation harness cannot detect the failures that matter**
`eval/run_ragas.py:55-62`. None of the seven query-time guard modules is imported or exercised
(§2.9). `false_refusal_rate: 0.0` in the stored results is measuring a pipeline users never hit.

**H8 — Rerank latency dominates and a global lock serializes all users**
`app/retrieval/reranker.py:26,45`; `app/ingestion/indexer.py:37,88`. 30–164 s per query inside a
process-wide mutex. Concurrent employees queue; an ingest blocks all chat. Effective throughput
≈ 1 query/minute.

**H9 — Citation hyperlinks are unusable for every employee except on the server**
`app/config/settings.py:44` (`api_public_base_url = http://localhost:8000`) +
`API_HOST=127.0.0.1`. Open WebUI binds `0.0.0.0` (`scripts/run_native.sh:89`) so employees reach
chat over the LAN — but every citation link then points at *their own* `localhost:8000`, where
nothing is listening. The README acknowledges the caveat in passing; in the intended multi-employee
deployment the flagship citation feature is broken for all of them.

### 🟡 Medium

| ID | Issue | Location |
|---|---|---|
| M10 | OCR / image / formula-OCR / figure extraction are empty stubs, while `CLAUDE.md` lists images and charts as supported inputs | `app/ingestion/parsers/{ocr,image_parser,formula_ocr,figure_extract}.py`; `router.py:62-63` |
| M11 | Formula verbalization is one sequential LLM call per math chunk, unbatched | `app/ingestion/enrichment.py:86-95` |
| M12 | `list_documents()` full-collection scroll, called per comparison query and per product-scope check, uncached | `indexer.py:330-365`; `comparison.py:87-94`; `product_scope.py:393-400` |
| M13 | No Qdrant payload indexes — all filters/counts are full scans | `indexer.py:100-115` |
| M14 | Upload read fully into memory; no size cap, no MIME validation | `api/ingest.py:197-201` |
| M15 | Docker path cannot run alongside native (3/4 ports collide); undocumented | `docker-compose.yml`, README |
| M16 | `Dockerfile` omits `COPY scripts/`, so the documented in-container knowledge-pack command cannot work | `Dockerfile:57-59` |
| M17 | Docker stack uses stock Open WebUI — no branding, no VI suggestions (parity gap) | `docker-compose.yml:77-95` |
| M18 | Branding patches `site-packages` in place; every `pip install --upgrade open-webui` reverts it | `scripts/open_webui/apply_branding.py` |
| M19 | Glossary holds only **10 terms** for a domain with hundreds; the skill names glossary entries as the primary fix for failed queries | `data/glossary/thuat_ngu.yaml` |
| M20 | Stale eval baseline (12 days, different model) and `citation_rate: 0.10` unaddressed | `eval/results/` |
| M21 | `PATCH /documents` rename runs a full synchronous re-ingest inside the request | `api/ingest.py:362-371` |
| M22 | No CI configuration in the repo | — |
| M23 | Only 6 of 7 synthetic documents were in the index at evaluation time, so the golden set could not fully resolve | `data/synthetic/` vs `GET /documents` |

### 🟢 Low

| ID | Issue | Location |
|---|---|---|
| L24 | `ruff format --check` fails on 2 files | `parsers/markdown.py`, `retrieval/product_scope.py` |
| L25 | `.venv` is Python 3.10.11 while docs mandate 3.11/3.12 | `scripts/setup_native.sh:6,20` |
| L26 | Section path repeats the document title in citations, producing very long link labels | `parsers/markdown.py:136-138` |
| L27 | No rate limit / lockout on `POST /login` | `app/api/login.py:30-43` |
| L28 | Stale Docker-era `qdrant_storage/{collections,aliases,raft_state.json}` (11 MB) beside the live `local/` store | `qdrant_storage/` |
| L29 | `vision_model`, `embed_model`, `ocr_language` settings declared but unread | `settings.py:74-75,200` |
| L30 | Inline citation format drifts from the numbered sources block | `prompts.py:98-102` vs `340-401` |
| L31 | `_MAX_HISTORY_TURNS = 6` hardcoded, contrary to the settings rule | `generator.py:40` |
| L32 | Weak admin password in the working `.env`; `.env.example` downplays the field | `.env` |
| L33 | Plain-string logging, no request IDs — concurrent requests are untangleable in `logs/api.log` | `app/main.py:30-31` |

---

## 4. Frontend assessment

### 4.1 Open WebUI customization — 7/10

**What exists.** `scripts/open_webui/apply_branding.py` (offline, idempotent, marker-delimited)
regenerates logo/favicon/splash PNGs with a BV mark in brand blue `#0072BC` + gold `#F7B928`,
injects a marker-fenced CSS block into the frontend `index.html`, sets the default locale to
`vi-VN`, and swaps the six stock English prompt suggestions for Vietnamese actuarial/internal ones.
Critically, it **backs up `webui.db` first, refuses to run while Open WebUI is up, and never
clobbers suggestions an admin edited by hand** (`--force` to override). That is careful, defensive
engineering for an unsupported customization path.

**Weaknesses.**
- It patches **pip-installed `site-packages` in place** — there is no supported hook in Open WebUI
  0.5.x. Any `pip install --upgrade open-webui` silently reverts logo, CSS and assets. The mitigation
  (re-run via `run_native.sh`) works only as long as upstream's file layout, CSS class names
  (`.bg-black` is relied on for the primary button colour) and DB schema hold.
- Prompt suggestions only appear **from the second start onward**, because Open WebUI creates its
  config DB on first boot. Documented, but a confusing first-run experience for the manager.
- Two of the six shipped suggestions currently return a refusal (C1) — the most visible surface in
  the product is demonstrating its worst bug.
- The admin dashboard (`app/static/index.html`, 745 lines, dependency-free, no CDN — correct for
  air-gap) is a separate surface from Open WebUI with its own look; there is no single pane of glass.

### 4.2 Docker ↔ native parity — 4/10

| Aspect | Native | Docker |
|---|---|---|
| Branding (logo/CSS/locale/suggestions) | ✅ applied by `run_native.sh` | ❌ stock image, unbranded |
| Qdrant | Embedded, single-process | Server mode |
| Ollama | Native, Metal GPU on Mac | In-compose, CPU-only on Mac |
| Ingest pipe valves | `localhost:8000` / `:3000` | must be changed to `api:8000` / `localhost:8080` |
| `scripts/` availability | ✅ | ❌ not copied into the image |
| Can run simultaneously | — | ❌ 3/4 ports collide |

The README is honest that "the Docker dev stack … is not branded", but the divergence is wider than
branding, and the two paths are presented as near-equivalent. Since deployment is Docker-free by
policy, the Docker path is now a **maintenance liability that is never validated**.

### 4.3 UX for non-technical staff — 7/10

**Pros.** Answers are Vietnamese end to end, including every error and refusal message. LaTeX
renders via KaTeX (verified: `$$_{t}V_{x} = A_{x+t} - P_{x}\cdot\ddot{a}_{x+t}$$` came back
correctly). The appended **Nguồn tham khảo** block always reflects the chunks actually in context,
with clickable titles — a genuinely good trust feature, and the "(nguồn công khai)" label for
knowledge-pack material is a thoughtful distinction. Upload is available inside the chat UI itself
via the Pipe function, so admins never need the port-8000 page day to day. The spellcheck
confirmation gate ("did you mean …?") is the right interaction for a Vietnamese no-diacritics
typing habit. Mermaid chart rules in the prompt give non-technical staff diagrams on request.

**Cons.**
- **43–95 s with no progress feedback** is the dominant UX problem. SSE streams tokens once
  generation starts, but the 45–70 s retrieval phase before the first token shows nothing.
- **Citation links are dead for LAN users** (H9).
- Citation labels repeat the document title inside the section path, producing very long, noisy
  link text (L26).
- A false refusal is indistinguishable from a genuine "not in the documents" — the user has no
  signal to retry differently.
- Pipe-function setup requires an admin to create an API key and paste a Python file into the
  Functions panel (`scripts/open_webui/README.md`) — ~2 minutes but well outside a
  non-technical manager's comfort zone, and it must be redone if the DB is reset.

### 4.4 Upgrade risk — **High**

Upgrading Open WebUI past 0.5.4 risks, in rough order of likelihood: prompt-suggestion schema
change in `webui.db` (the script writes it directly via `sqlite3`); asset path/filename changes
breaking the PNG regeneration; Tailwind class churn breaking `.bg-black` recolouring;
`index.html` structure changes breaking CSS injection; and Pipe-function API changes breaking
`ingest_pipe.py`. Because `WEBUI_AUTH` cannot be flipped back to `false` once users exist, a failed
upgrade is also awkward to roll back. **Recommendation: pin `open-webui` exactly in a
`requirements-webui.txt`, and treat upgrades as a planned, tested change — never routine.**

---

## 5. Improvement roadmap

All items are zero-budget, fully offline, no paid services.

### 5.1 Quick wins (< 1 day each)

| Pri | Item | Why / how |
|---|---|---|
| 1 | **Neutralize C1 immediately**, then fix properly | Ship `PRODUCT_SCOPE_GUARD_ENABLED=false` as a one-line stopgap. Proper fix: only fire the guard when the extracted span resolves to a *known indexed product title* — reuse `mentioned_doc_titles`/`named_product_labels`, which already gets this right — and require ≥2 distinctive tokens. Add the 3 failing golden-set questions + the 2 prompt suggestions as regression tests. |
| 2 | **Send `num_ctx`** (C3) | One line in `_ollama_payload`: `"num_ctx": settings.llm_context_window`. Verify with `ollama ps`. Consider raising to 12288 given 5×800-token chunks. |
| 3 | **Isolate tests from `.env`** (C2) | A `conftest.py` fixture that clears `ADMIN_PASSWORD` (or constructs `Settings(_env_file=None)`), plus an authenticated `TestClient` fixture so the gate itself stays covered. |
| 4 | **Populate `page`** (H5) | Docling exposes per-item provenance; map it onto `ParsedSection.page` in `pdf_parser`. Unlocks the already-written `#page=N` deep-linking. |
| 5 | **Fix LAN citations** (H9) | Document + default `API_PUBLIC_BASE_URL` to the machine's LAN address, and bind `API_HOST=0.0.0.0` *only* for the two public read-only doc routes (or front them via Open WebUI). Add a startup warning when `api_public_base_url` is loopback while Open WebUI binds `0.0.0.0`. |
| 6 | **Cap comparison damage** (H6) | Require each candidate label to resolve to ≥1 indexed doc title before spending a retrieval pass; drop labels that resolve to nothing. Cheap, removes the two garbage passes and ~two-thirds of that query's 164 s. |
| 7 | Grow the glossary from 10 → 60–100 terms | The skill names this as the first-line fix for failed queries; it is pure YAML, no code, and improves both expansion and definition answers. |
| 8 | `ruff format`; delete stale `qdrant_storage/{collections,aliases,raft_state.json}`; move `_MAX_HISTORY_TURNS` into settings; strengthen the `.env` admin password | Housekeeping (L24, L28, L31, L32). |

### 5.2 Medium term (≈ 1 week each)

| Pri | Item | Why / how |
|---|---|---|
| 1 | **Parent-child ("small-to-big") chunking** (H4) | Keep today's small, precise units as the *retrieval* index; attach a `parent_id` and store the enclosing section (or a merged 500–800-token window) as the text handed to generation. Also honour `CHUNK_MIN_TOKENS` by merging adjacent sibling sections under a shared heading before packing. This is the single largest quality lever and it fixes the dangling-reference problem without hurting citation precision. |
| 2 | **Cut rerank latency 5–10×** (H8) | In order of effort: (a) rerank only the top 12–15 fused candidates instead of up to 40; (b) export bge-reranker-v2-m3 to **ONNX + INT8 dynamic quantization** and run it under `onnxruntime` — typically 3–5× on CPU with negligible quality loss, fully offline; (c) batch pairs in one `compute_score` call; (d) add a cheap pre-filter (RRF score cutoff) before the cross-encoder. Combined with (1) reducing candidate count, sub-10 s retrieval is realistic. |
| 3 | **Make the eval harness test the real pipeline** (H7) | Point `run_ragas.py` at `chat._retrieve` (or better, at `POST /v1/chat/completions` over HTTP) so every guard is in the loop. Add a **`false_refusal`** category with the questions from C1, and assert `false_refusal_rate == 0` as a gate. Re-baseline on `qwen3:8b`. One command: `make eval`. |
| 4 | **Fix `citation_rate: 0.10`** | Measure first, then either strengthen rule 2 with a worked example in the prompt, or post-process: map the model's `[n]` markers onto the sources block and reject/repair answers with zero citations. |
| 5 | **Serve concurrency properly** (H8) | Move embedding + reranking into a small worker pool (2–3 processes, each with its own model instance) behind a queue, replacing the process-wide mutex. Add a request queue depth limit + friendly "đang xử lý" response. |
| 6 | **Auto-ingest + CI** | A `watchdog`-based folder watcher (or a cron calling `scripts/ingest.sh`) that ingests new files into a configured drop directory and logs results. CI: a local `pre-commit`/`make check` running `ruff check`, `ruff format --check`, `pytest`, and a retrieval-only eval smoke test — no cloud runner needed. |
| 7 | **Qdrant payload indexes + cache `list_documents()`** (M12, M13) | `create_payload_index` on `doc_id`, `doc_type`, `department`; TTL-cache the document list (invalidate on ingest/delete). Removes repeated full scans from the hot query path. |
| 8 | **Batch enrichment** (M11) | Group math chunks and issue one Ollama call per batch; parallelize with a small bounded pool. Cuts ingest wall time materially. |
| 9 | **Upload hardening** (M14) | Stream to disk in chunks, enforce `MAX_UPLOAD_MB` from settings, validate magic bytes against the extension. |

### 5.3 Long term

| Item | Notes |
|---|---|
| **Implement the OCR / figure slice** (M10) | PaddleOCR (`lang="vi"`) + PP-FormulaNet or Qwen2.5-VL for formula regions; figure extraction from Docling regions with VLM descriptions indexed as `doc_type: figure`. Until then, correct `CLAUDE.md`/README so images are not advertised as supported. Include the glossary cross-check for pre-subscript notation and actually set `needs_review`. |
| **Quality feedback loop** | Persist per-query records (question, standalone query, hits + scores, guard decisions, answer, latency) to a local SQLite table. Add 👍/👎 to Open WebUI (native feature) and export it. A small static dashboard over that table gives refusal rate, latency percentiles, and the top failing queries — the input that should drive glossary and chunking work. Strictly local; no telemetry. |
| **Agentic upgrades** | (a) Tool calling for a deterministic **actuarial calculator** so arithmetic leaves the LLM entirely — this also strengthens rule 4. (b) Structured querying over XLSX: index sheets into a local SQLite table alongside the Markdown rendering and let the model emit SQL for aggregate questions ("tổng chi trả quý 1"), which today's row-chunk retrieval cannot answer. (c) Multi-step decomposition for calculation questions (retrieve formula → retrieve parameters → compute via tool → verify). |
| **Model & quantization strategy** | Benchmark `qwen3:4b` and Q4 quantizations against the golden set; publish a hardware→model matrix in the README (the 16 GB box is at ~15.6 GB today). Add a startup check that warns when free RAM is below the chosen model's needs. |
| **Auto-reindex on model change** | Store `embed_model` + a chunking-config hash in the collection metadata; warn (or offer re-index) at startup when they differ from `settings` — silently mixing bge-m3 vectors with a different embedder would be an invisible catastrophe. |
| **Decide the Docker question** | Either restore parity (branding in the image, `COPY scripts/`, documented port handling, a compose profile that coexists with native) or retire `docker-compose*.yml` + `Dockerfile` to a `dev/` folder marked unsupported. Maintaining an unvalidated second path costs more than it returns. |
| **Retrieval accuracy, next tier** | Query rewriting is already there; add (a) HyDE-style pseudo-answer expansion for terse queries, (b) automatic `doc_type`/`department` metadata filtering inferred from the question, (c) sentence-window retrieval for exclusion clauses specifically, (d) a proper BM25 sidecar if bge-m3 sparse proves weak on rare product codes. |

---

## Appendix — how each claim was verified

| Claim | Method |
|---|---|
| Service health, model serving | `GET /health`, `GET /v1/models`, `ollama ps`, `logs/api.log` warmup lines |
| Stage latencies | `retrieval timings` / `generation timings` log lines emitted by `chat.py:241` and `generator.py:356` |
| End-to-end latency & answer quality | 6 live `POST /v1/chat/completions` calls (`stream:false`) |
| Chunk size distribution, `page=None` | Read-only copy of `qdrant_storage/local` opened with `qdrant-client`; 123 points scrolled; tokens via the project's own `default_token_counter` |
| C1 false refusals | Direct calls to `product_scope.query_names_absent_product` / `_product_spans` over the full golden set and `prompt_suggestions.json` |
| H6 garbage comparison labels | `comparison retrieval: product=…` lines in `logs/api.log` |
| C2 test failures | `.venv/bin/python -m pytest tests/ -q` |
| C3 context window | `grep` for `llm_context_window`/`num_ctx` across `app/`; `ollama ps` CONTEXT column |
| Air-gap integrity | `grep` for all HTTP client calls in `app/`; `git ls-files` for tracked secrets; `data/real/` listing |
| Ingestion timings | Timed `POST /ingest` for each synthetic file; Docling's own `Finished converting … in 124.53 sec` |
| Docker validity | `docker compose config`; isolated `docker compose up -d qdrant` + `healthz` + teardown |
| Memory | `top -l 1 -pid <api>`, `ps` RSS for `llama-server`, `sysctl hw.memsize` |
