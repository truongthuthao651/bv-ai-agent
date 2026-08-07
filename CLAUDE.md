# CLAUDE.md — Local RAG Assistant for a Vietnamese Life Insurance Firm

## What this project is

An internal, fully-local AI assistant (ChatGPT-like) that answers employees'
questions about company documents. Everything runs offline on one machine.
Zero budget: only free/open-source tools. **Deployment is Docker-free**
(company machines don't allow Docker): native venvs + Ollama, with Qdrant
running EMBEDDED in-process (qdrant-client local mode, `QDRANT_LOCAL_PATH`).
Docker Compose remains as an optional dev-machine stack.

- **Inputs:** text questions, PDF / DOCX / XLSX documents, images (scans, screenshots).
  Documents are math-heavy: actuarial terminology, equations, charts.
- **Output:** grounded answers in Vietnamese with source citations; formulas rendered as LaTeX
- **Serving:** Ollama (chat: `qwen3:8b`, vision: `qwen2.5vl:7b`, embeddings: `bge-m3`)
- **Vector DB:** Qdrant (hybrid dense + sparse retrieval), reranker `bge-reranker-v2-m3`;
  embedded in-process on deployment (`QDRANT_LOCAL_PATH`), server mode in Docker dev
- **Parsing:** Docling with formula enrichment (PDF), pandoc (DOCX → Markdown+LaTeX),
  pandas/openpyxl (XLSX → Markdown tables), PaddleOCR + PP-FormulaNet or Qwen2.5-VL
  (scans & formula OCR, Vietnamese)
- **Backend:** FastAPI (SSE streaming, OpenAI-compatible `/v1/chat/completions`)
- **Frontend:** Open WebUI pointed at the FastAPI endpoint (renders LaTeX via KaTeX natively)

## Canonical document representation

ALL parsers converge to **Markdown with LaTeX math** (`$...$` inline, `$$...$$` display).
Chunking, enrichment, embedding, and display only ever deal with this one format.

## 🔒 NON-NEGOTIABLE SECURITY RULES

1. **NEVER read, open, list, or reference anything under `data/real/`.** That
   directory may contain confidential company documents on the deployment
   machine. All development and testing uses `data/synthetic/` only.
2. Never add real document content, names, policy numbers, or amounts to code,
   tests, fixtures, logs, commit messages, or this file. (Textbook actuarial
   formulas and standard terminology are NOT confidential and are fine.)
3. `data/`, `.env`, `models/`, `qdrant_storage/` are gitignored — never force-add
   them. Exception: `data/glossary/` IS committed (public terminology only).
4. No external API calls in application code. The app must work air-gapped.
   Allowed network use at setup time only: `ollama pull`, `pip install`, HF model download.
   No web search, no runtime document fetching. Public reference material reaches
   the assistant via the **offline knowledge pack** instead: a human downloads the
   public files by hand into `data/knowledge_pack/`, records each one's public URL
   in `manifest.yaml`, and `scripts/ingest_knowledge_pack.py` indexes them locally.
   The recorded `source_url` is only ever *rendered* as the citation link — never
   requested by the app.
5. Do not add telemetry or analytics of any kind.

## Project structure

```
bv-ai-agent/
├── CLAUDE.md
├── README.md                  # Bilingual (VI first) — written for the manager who deploys
├── .env.example               # Template; each machine copies to .env
├── .gitignore
├── docker-compose.yml         # CPU-safe baseline (ollama, qdrant, api, open-webui)
├── docker-compose.gpu.yml     # Override adding NVIDIA GPU to ollama
├── Dockerfile                 # FastAPI app image (python:3.12-slim + pandoc)
├── requirements.txt           # Pinned versions
├── .claude/
│   └── skills/
│       └── insurance-rag-pipeline/
│           └── SKILL.md
├── app/
│   ├── main.py                # FastAPI entrypoint, routers, lifespan (model warmup);
│   │                          #   mounts app/static/ (admin UI) at "/"
│   ├── auth.py                # Single-password session gate for the admin UI (ADMIN_PASSWORD);
│   │                          #   opt-in API_SHARED_SECRET gate for /v1/* (SEC1)
│   ├── query_timing.py        # "⏱ Thời gian trả lời" footer + logs/query_timings.jsonl
│   │                          #   (metadata-only: doc_id/section_path/score/plan flags, ADM1)
│   ├── text_utils.py          # fold_text: shared diacritic-fold used by every guard
│   ├── config/
│   │   └── settings.py        # pydantic-settings; ALL config flows through here
│   ├── api/
│   │   ├── chat.py            # POST /v1/chat/completions (OpenAI-compatible, SSE)
│   │   ├── ingest.py          # POST /ingest (file upload, size-capped), GET/PATCH/DELETE /documents
│   │   ├── health.py          # GET /health — pings ollama + qdrant
│   │   ├── login.py           # GET/POST /login, POST /logout (admin session)
│   │   ├── docview.py         # GET /documents/{id}/view — reconstructs a doc from its
│   │   │                      #   indexed chunks so citation links always resolve
│   │   └── metrics.py         # GET /metrics/summary — aggregates query_timings.jsonl
│   │                          #   (refusal rate, latency percentiles, mode breakdown; ADM1)
│   ├── static/
│   │   └── index.html         # Dependency-free admin UI: upload/list/edit/delete docs,
│   │                          #   quick-ask test, "Chất lượng & hiệu năng" metrics view
│   ├── templates/
│   │   └── login.html         # Branded admin login page
│   ├── ingestion/
│   │   ├── router.py          # File-type detection → correct parser
│   │   ├── metric_hints.py    # Deterministic metric-type hint appended to embed_text
│   │   │                      #   (lãi suất cam kết ≠ tỷ lệ bồi thường); no LLM
│   │   ├── parsers/
│   │   │   ├── pdf_parser.py      # Docling, do_formula_enrichment=True; OCR fallback
│   │   │   ├── docx_parser.py     # pandoc → gfm+tex_math_dollars (preserves OMML equations)
│   │   │   ├── xlsx_parser.py     # Sheet → Markdown table, header repeated per chunk
│   │   │   ├── glossary_parser.py # .yaml/.yml → ParsedDocument(doc_type=GLOSSARY)
│   │   │   ├── markdown.py        # Shared Điều/Khoản-aware sectionizer every parser uses
│   │   │   ├── image_parser.py    # STUB — PaddleOCR + formula regions + optional VLM caption
│   │   │   ├── formula_ocr.py     # STUB — PP-FormulaNet / Qwen2.5-VL region → LaTeX
│   │   │   ├── figure_extract.py  # STUB — pull figure images out of PDFs (Docling regions)
│   │   │   └── ocr.py             # STUB — shared PaddleOCR wrapper (lang="vi")
│   │   ├── cleaning.py        # NFC Unicode normalization, header/footer strip
│   │   ├── chunking.py        # Heading-aware split (Điều/Khoản/Điểm), 500–800 tok,
│   │   │                      #   10–15% overlap; NEVER splits equations (see skill);
│   │   │                      #   parent-child: small children indexed, parent generated
│   │   ├── enrichment.py      # LLM verbalization of formulas (VI) + VLM figure
│   │   │                      #   descriptions; produces embed_text vs display_text
│   │   └── indexer.py         # bge-m3 embed (dense+sparse) → Qdrant upsert
│   ├── retrieval/
│   │   ├── retriever.py       # Hybrid search top-20, RRF fusion, metadata filters
│   │   ├── reranker.py        # bge-reranker-v2-m3 → top-5
│   │   ├── query_expansion.py # Glossary-based synonym expansion (no LLM call)
│   │   ├── query_rewrite.py   # Standalone-question rewriting from chat history
│   │   ├── spellcheck.py      # Typo gate: confirm a misspelt term before answering
│   │   ├── product_scope.py   # Refuse when a named product is absent from the docs;
│   │   │                      #   mentioned_doc_titles() = informal-mention + corpus-
│   │   │                      #   relative dynamic title-distinctiveness matching
│   │   ├── conversation_scope.py # Sticky product across follow-up turns (reuses
│   │   │                      #   product_scope's informal-title matching, not just
│   │   │                      #   cue-phrase parsing)
│   │   ├── comparison.py      # Multi-product turns: per-product retrieval quota
│   │   ├── metric_guard.py    # Drop table metrics the question didn't ask for
│   │   └── coverage.py        # "Có được chi trả?": benefit terms in the query,
│   │                          #   backfill the payout clause, put benefits first
│   ├── generation/
│   │   ├── prompts.py         # Vietnamese system prompts, citation format, math rules
│   │   ├── advisory.py        # Detect comparison/recommendation turns → advisory prompt
│   │   ├── coverage_gate.py   # Post-generation: a coverage verdict citing no
│   │   │                      #   benefit clause is regenerated, then replaced
│   │   ├── verify.py          # Second LLM pass on a finished coverage answer: invented
│   │   │                      #   facts, or a conclusion against its own cited clause
│   │   ├── citations.py       # Dangling-[n] check: strip (non-streaming) or flag
│   │   │                      #   (streaming) a citation that resolves to no source (ADM2)
│   │   ├── history.py         # Strip our appended suffixes before replaying a turn
│   │   └── generator.py       # Ollama call, streaming, context assembly
│   └── models/
│       └── schemas.py         # Pydantic request/response models
├── scripts/
│   ├── setup_native.sh        # One-time no-Docker setup: venvs + models (deployment path)
│   ├── run_native.sh          # Start ollama/API/Open WebUI natively (embedded Qdrant);
│   │                          #   suggests a LAN API_PUBLIC_BASE_URL when API_HOST=0.0.0.0
│   ├── stop_native.sh         # Stop what run_native.sh started (pid files in run/)
│   ├── setup_models.sh        # ollama pull + HF downloads (native/docker autodetect)
│   ├── ingest.sh              # Batch-ingest a folder
│   ├── ingest_knowledge_pack.py  # Index manually-downloaded PUBLIC refs + their URLs
│   ├── healthcheck.sh         # Smoke test: ollama, qdrant, api, webui
│   ├── check.sh               # Local CI-equivalent: ruff check + format --check + pytest
│   ├── chunk_stats.py         # Parent/child chunk sizes for a folder (budget tuning)
│   ├── make_synthetic_data.py # Fake VI insurance docs incl. actuarial formulas & charts
│   └── open_webui/            # Bảo Việt branding + the "Nạp tài liệu" ingest pipe for Open WebUI
├── data/                      # GITIGNORED except glossary/ + the pack manifest template
│   ├── glossary/
│   │   └── thuat_ngu.yaml     # Actuarial term glossary: term, synonyms, symbol, definition
│   ├── knowledge_pack/        # PUBLIC refs downloaded by hand (law, circulars, brochures)
│   │   └── manifest.example.yaml  # Template: file → title + public url (committed)
│   ├── synthetic/             # Fake docs — the ONLY data used in dev/tests
│   └── real/                  # Exists only on the company machine — NEVER touch
├── eval/
│   ├── golden_set.jsonl       # Q/A pairs incl. formula, notation, figure, and "adversarial"
│   │                          #   (category) items, one per documented historical failure
│   │                          #   mode; must_say/must_not_say = the deterministic safety
│   │                          #   gate — an entry may be a list of accepted alternatives
│   └── run_ragas.py           # Context precision/recall, rule compliance, --strict gate
├── docs/
│   ├── TEAMMATE_GUIDE.md      # Bilingual (VI-first) onboarding doc for a human teammate
│   └── audit/                 # Dated audit reports + the one-week roadmap this file's
│                              #   "Conventions"/rules above were partly born from
└── tests/
    ├── test_parsers.py        # Incl. OMML→LaTeX and formula-OCR cases
    ├── test_chunking.py       # Incl. never-split-equation cases
    ├── test_enrichment.py
    ├── test_retrieval.py      # Incl. glossary expansion cases
    └── fixtures/              # Tiny synthetic files only (incl. math-heavy samples)
```

## Conventions

- **Config:** every tunable value goes through `app/config/settings.py`
  (pydantic-settings reading `.env`). Never `os.getenv()` elsewhere; never
  hardcode URLs, model names, or paths.
- **Vietnamese text:** always NFC-normalize on ingestion (`unicodedata.normalize("NFC", s)`).
  Watch for legacy TCVN3/VNI encodings in old DOCX files.
- **User-facing strings and prompts:** Vietnamese. Code, comments, commit messages: English.
- **Math:** equations are LaTeX in Markdown, never split across chunks, always kept
  with their defining paragraph ("trong đó: ..."). Every formula chunk gets a
  Vietnamese verbalization for embedding (see enrichment). Actuarial pre-subscript
  notation (e.g. `{}_np_x`) is error-prone in OCR — cross-check against glossary symbols.
- **Chunk fields:** each chunk has `embed_text` (prose + LaTeX + verbalization —
  what bge-m3 sees) and `display_text` (clean Markdown+LaTeX — the unit that is
  retrieved and reranked). Qdrant payload: `doc_id, doc_title, section_path, page,
  department, doc_type, parent_text (optional), parent_index (optional),
  figure_image_path (optional), ingested_at`.
  `doc_type ∈ {policy, procedure, form, spreadsheet, image, figure, glossary,
  reference, other}` (`reference` = public knowledge-pack material).
  Knowledge-pack chunks also carry `source_url` (the public page the file was
  downloaded from); citations then link there, labeled `(nguồn công khai)`.
  Prepend `"Tài liệu: {doc_title} > {section_path}"` to embed_text.
- **Parent-child chunking** (`PARENT_CHILD_CHUNKING_ENABLED`): each indexed point
  is a small child (`CHUNK_CHILD_MAX_TOKENS`) cut from a normal 500–800 token
  parent. The child is embedded and reranked; generation reads
  `payload.context_text` (the parent when there is one). Parents are exactly the
  chunks the flat path produces, so disabling the flag restores it. The reranker
  keeps one child per parent before the top-k cut, and any guard inspecting chunk
  text must use `context_text` — that is what the model receives.
- **Answering rules:** answer only from retrieved context; cite as `[n]` — the
  number of the context block the fact came from, which `prompts.citation_numbers`
  keeps identical to that source's number in the "Nguồn tham khảo" block, so
  every marker resolves to a clickable line (never invent a number); reply
  "Tôi không tìm thấy thông tin trong tài liệu"
  when context is insufficient; for numeric calculations, show the formula and
  substitution steps but state results must be verified with official tools
  ("Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức"); never
  invert exclusion clauses (loại trừ / không chi trả → must conclude NOT covered)
  nor over-apply them (an exclusion applies only when the event matches its
  stated conditions — never conclude NOT covered just because an exclusion
  section was retrieved, never invent exclusions);
  never remap table metrics (lãi suất cam kết / phí ≠ tỷ lệ bồi thường).
  Never weaken these in prompts.py.
- **Coverage questions are answered by ENUMERATING CASES, not by one verdict.**
  "Tôi bị X thì có được chi trả không?" is almost always underdetermined by the
  documents: the outcome depends on which benefit the event triggers (tử vong /
  thương tật toàn bộ vĩnh viễn / nằm viện), on riders, and on conditions the
  employee hasn't stated. The answer must lay out the branches the retrieved
  documents actually define — each with its citation — then name what is still
  needed to decide, and say plainly which parts the documents do not cover.
  A single flat "được" / "không được" on an underdetermined question is a
  DEFECT even when it happens to land on the right side.
- **An exclusion list is not a coverage list.** "Loại trừ trách nhiệm bảo hiểm"
  enumerates only what is NOT paid. An event's absence from it means the event
  is NOT EXCLUDED — never that it is not covered. The inference "X không có
  trong mục loại trừ ⇒ X không được chi trả" is exactly backwards and is banned
  in prompt rule 6(c). Coverage is decided from the benefit clauses ("Quyền lợi
  tử vong", "Công ty chi trả ..."), which must be cited when present. Real-doc
  failure, 2026-07-27: asked whether death was covered, the model answered
  "không được chi trả" because death "không được liệt kê ... trong mục Loại
  trừ" — while the death-benefit clause sat at rank 3 of its own context,
  uncited. Rank 1 was the exclusions page; the model cites what it reads first,
  so coverage answers put benefit clauses first (`coverage.payout_clauses_first`).
- **Insufficient context is never evidence of exclusion.** When the retrieved
  context contains ONLY exclusion clauses and no benefit / scope clause, the
  model has not found grounds to deny — it has failed to retrieve the coverage
  side. Say the documents don't state it (and what would answer it); never
  conclude "không được chi trả" from an absence. Real-doc failure, 2026-07-27:
  a travel car-accident question retrieved one exclusion section and nothing
  else, and the answer denied the claim by applying "loại trừ bổ sung" (a
  substandard-health underwriting clause) to a car accident — while its own
  general-knowledge block said the case could not be determined. Prompt rule
  6(b) already forbade this in as many words, so treat prompt text as
  insufficient on its own: an exclusion-only context needs a retrieval fix
  (pull the benefit/scope clause too) and/or a deterministic guard.
- **A coverage verdict must cite a benefit clause, or it does not ship.**
  Retrieval-side fixes proved insufficient: in a 4-turn conversation on a real
  policy (2026-07-27), with the benefit clause backfilled into context AND
  moved to rank 1 by `coverage.payout_clauses_first`, the answer denied the
  claim in all four turns citing only the exclusions page — "QUYỀN LỢI TỬ
  VONG" sat uncited at [1]/[2] every time, including on "tai nạn xe tử vong",
  which that clause answers outright. On pushback it flipped to "Có được
  claim" on the same evidence, still uncited: absence-reasoning landing the
  other way. So `app/generation/coverage_gate.py` checks the FINISHED answer —
  a "được/không được chi trả" verdict that cites no benefit clause present in
  its own context is regenerated once with a corrective turn, then replaced by
  a deterministic enumeration of the branches. Coverage turns therefore answer
  in one block instead of streaming (the verdict is only checkable when
  complete). Never trust a prompt block alone to prevent a verdict; the model
  reached the banned conclusion twice *with* a block forbidding it verbatim.
- **The "Kiến thức chung" block may never contradict the grounded answer.** If
  it says the case cannot be determined, the grounded part must not have
  asserted a verdict.
- **Never replay our own appended suffixes back to the model.** Open WebUI
  returns the rendered answer, so the sources block, the disclaimers and the
  "⏱ Thời gian trả lời" footer all come back as assistant content.
  `generation/history.py` strips them in `build_messages`; the raw turns stay
  intact for `conversation_scope` / `comparison`, which deliberately parse the
  sources block to recover a chat's products. Real-doc failure, 2026-07-27:
  replaying them taught the model to write its own "Nguồn tham khảo" block
  under its own numbering — three source blocks in one answer by turn 4, the
  model's [1] and ours naming different sections, so no citation resolved.
  A model-written block is also truncated on the way out (`SourcesTruncator`).
- **Answer modes:** `prompts.system_prompt()` assembles one grounded prompt from
  shared rule blocks. *Strict* (default) answers only from context. *Advisory*
  (comparison / "KH nên chọn sản phẩm nào?" — routed by
  `app/generation/advisory.py`) keeps every datum sourced from context and keeps
  the wrong-product refusal, but may reason across the retrieved facts and give
  conditional recommendations; it is labeled `ADVISORY_DISCLAIMER`. Either may
  append ONE fenced "Kiến thức chung (ngoài tài liệu)" section of textbook
  knowledge (`GENERAL_KNOWLEDGE_SUPPLEMENT_ENABLED`), labeled and never a
  substitute for the grounded part. Rules 2 and 4-7 are shared blocks — changing
  them applies to both modes by construction; never fork them.
  Both modes aim for an ANSWER SHAPE closer to a good human adviser than to a
  one-line verdict: state the conclusion (or that it depends), enumerate the
  cases with their conditions, cite each, and end with what the employee should
  check next. Brevity is not the goal — being *actionable and correct* is; the
  `_FOOTER` "ngắn gọn" instruction must not be read as license to collapse a
  multi-branch answer into one sentence.
- **Versions:** pin everything (requirements.txt exact versions, Docker image tags).
  Never use `:latest`.
- **Style:** type hints everywhere, `ruff` for lint/format, small pure functions
  in ingestion/ so they're unit-testable without Docker.

## Commands

```bash
bash scripts/setup_native.sh                                # one-time native setup (venvs + models)
bash scripts/run_native.sh                                  # start stack natively (no Docker)
bash scripts/stop_native.sh                                 # stop the native stack
bash scripts/setup_models.sh                                # pull all models (native/docker autodetect)
bash scripts/healthcheck.sh                                 # smoke test
python scripts/make_synthetic_data.py                       # regenerate fake docs
python scripts/chunk_stats.py data/synthetic                # parent/child chunk sizes (tuning)
bash scripts/ingest.sh data/synthetic                       # index synthetic corpus
bash scripts/ingest.sh data/glossary                        # index the glossary
python scripts/ingest_knowledge_pack.py --dry-run           # validate the pack manifest
python scripts/ingest_knowledge_pack.py                     # index public reference docs
pytest tests/ -x -q                                         # unit tests (no services needed)
python eval/run_ragas.py                                    # RAG quality metrics (native: stop the API first — embedded Qdrant is single-process)
python eval/run_ragas.py --strict                            # same, but exit non-zero on a gate failure (CI / pre-merge)
ruff check app/ && ruff format app/                         # lint + format
bash scripts/check.sh                                        # local CI-equivalent: ruff check + format --check + pytest
docker compose up -d                                        # optional Docker dev stack (CPU)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d   # with GPU
```

## Environment notes

- Dev happens on a personal laptop; deployment is `git clone` + `.env` +
  `scripts/setup_native.sh` / `run_native.sh` on a company laptop by the manager
  — **no Docker there** (company policy). Anything machine-specific belongs in
  `.env`, never in code. Keep README deployment steps up to date whenever setup
  changes.
- Deployment needs only Python 3.11/3.12 and Ollama installed. Everything else
  is pip-installed into `.venv` (app; pandoc bundled via `pypandoc-binary`) and
  `.venv-webui` (Open WebUI), and Qdrant runs embedded in the API process
  (`QDRANT_LOCAL_PATH` — single-process storage: stop the API before running
  `eval/run_ragas.py` natively).
- Hardware varies: default model is set by `CHAT_MODEL` in `.env` so weak machines
  can drop to `qwen3:4b` without code changes.
- Enrichment (formula verbalization, figure description) makes ingestion slow —
  that's fine, it's offline batch work. Never move enrichment to query time.
