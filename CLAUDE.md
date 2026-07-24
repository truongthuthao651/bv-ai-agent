# CLAUDE.md — Local RAG Assistant for a Vietnamese Life Insurance Firm

## What this project is

An internal, fully-local AI assistant (ChatGPT-like) that answers employees'
questions about company documents. Everything runs offline on one machine.
Zero budget: only free/open-source tools. Deployment uses native virtual
environments plus Ollama, with Qdrant running EMBEDDED in-process
(qdrant-client local mode, `QDRANT_LOCAL_PATH`).

- **Inputs:** text questions, PDF / DOCX / XLSX documents, images (scans, screenshots).
  Documents are math-heavy: actuarial terminology, equations, charts.
- **Output:** grounded answers in Vietnamese with source citations; formulas rendered as LaTeX
- **Serving:** Ollama (chat: `qwen3:8b`, vision: `qwen2.5vl:7b`, embeddings: `bge-m3`)
- **Vector DB:** Qdrant (hybrid dense + sparse retrieval), reranker `bge-reranker-v2-m3`;
  embedded in-process by default (`QDRANT_LOCAL_PATH`)
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
5. Do not add telemetry or analytics of any kind.

## Project structure

```
bv-ai-agent/
├── CLAUDE.md
├── README.md                  # Bilingual (VI first) — written for the manager who deploys
├── .env.example               # Template; each machine copies to .env
├── .gitignore
├── requirements.txt           # Pinned versions
├── .claude/
│   └── skills/
│       └── insurance-rag-pipeline/
│           └── SKILL.md
├── app/
│   ├── main.py                # FastAPI entrypoint, routers, lifespan (model warmup)
│   ├── config/
│   │   └── settings.py        # pydantic-settings; ALL config flows through here
│   ├── api/
│   │   ├── chat.py            # POST /v1/chat/completions (OpenAI-compatible, SSE)
│   │   ├── ingest.py          # POST /ingest (file upload), GET /documents
│   │   └── health.py          # GET /health — pings ollama + qdrant
│   ├── ingestion/
│   │   ├── router.py          # File-type detection → correct parser
│   │   ├── parsers/
│   │   │   ├── pdf_parser.py      # Docling, do_formula_enrichment=True; OCR fallback
│   │   │   ├── docx_parser.py     # pandoc → gfm+tex_math_dollars (preserves OMML equations)
│   │   │   ├── xlsx_parser.py     # Sheet → Markdown table, header repeated per chunk
│   │   │   ├── image_parser.py    # PaddleOCR + formula regions + optional VLM caption
│   │   │   ├── formula_ocr.py     # PP-FormulaNet / Qwen2.5-VL region → LaTeX
│   │   │   ├── figure_extract.py  # Pull figure images out of PDFs (Docling regions)
│   │   │   └── ocr.py             # Shared PaddleOCR wrapper (lang="vi")
│   │   ├── cleaning.py        # NFC Unicode normalization, header/footer strip
│   │   ├── chunking.py        # Heading-aware split (Điều/Khoản/Điểm), 500–800 tok,
│   │   │                      #   10–15% overlap; NEVER splits equations (see skill)
│   │   ├── enrichment.py      # LLM verbalization of formulas (VI) + VLM figure
│   │   │                      #   descriptions; produces embed_text vs display_text
│   │   └── indexer.py         # bge-m3 embed (dense+sparse) → Qdrant upsert
│   ├── retrieval/
│   │   ├── retriever.py       # Hybrid search top-20, RRF fusion, metadata filters
│   │   ├── reranker.py        # bge-reranker-v2-m3 → top-5
│   │   ├── query_expansion.py # Glossary-based synonym expansion (no LLM call)
│   │   └── query_rewrite.py   # Standalone-question rewriting from chat history
│   ├── generation/
│   │   ├── prompts.py         # Vietnamese system prompts, citation format, math rules
│   │   └── generator.py       # Ollama call, streaming, context assembly
│   └── models/
│       └── schemas.py         # Pydantic request/response models
├── scripts/
│   ├── setup_native.sh        # One-time native setup: venvs + models
│   ├── run_native.sh          # Start ollama/API/Open WebUI natively (embedded Qdrant)
│   ├── stop_native.sh         # Stop what run_native.sh started (pid files in run/)
│   ├── setup_models.sh        # ollama pull + HF downloads
│   ├── ingest.sh              # Batch-ingest a folder
│   ├── healthcheck.sh         # Smoke test: ollama, qdrant, api, webui
│   └── make_synthetic_data.py # Fake VI insurance docs incl. actuarial formulas & charts
├── data/                      # GITIGNORED except glossary/
│   ├── glossary/
│   │   └── thuat_ngu.yaml     # Actuarial term glossary: term, synonyms, symbol, definition
│   ├── synthetic/             # Fake docs — the ONLY data used in dev/tests
│   └── real/                  # Exists only on the company machine — NEVER touch
├── eval/
│   ├── golden_set.jsonl       # Q/A pairs incl. formula, notation, and figure questions
│   └── run_ragas.py           # Faithfulness, answer relevancy, context precision/recall
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
  what bge-m3 sees) and `display_text` (clean Markdown+LaTeX — what goes into the
  generation context). Qdrant payload: `doc_id, doc_title, section_path, page,
  department, doc_type, figure_image_path (optional), ingested_at`.
  `doc_type ∈ {policy, procedure, form, spreadsheet, image, figure, glossary, other}`.
  Prepend `"Tài liệu: {doc_title} > {section_path}"` to embed_text.
- **Answering rules:** answer only from retrieved context; cite as
  `[Tên tài liệu, mục X]`; reply "Tôi không tìm thấy thông tin trong tài liệu"
  when context is insufficient; for numeric calculations, show the formula and
  substitution steps but state results must be verified with official tools
  ("Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức"); never
  invert exclusion clauses (loại trừ / không chi trả → must conclude NOT covered)
  nor over-apply them (an exclusion applies only when the event matches its
  stated conditions — never conclude NOT covered just because an exclusion
  section was retrieved, never invent exclusions);
  never remap table metrics (lãi suất cam kết / phí ≠ tỷ lệ bồi thường).
  Never weaken these in prompts.py.
- **Versions:** pin every Python dependency exactly. Never use unbounded ranges.
- **Style:** type hints everywhere, `ruff` for lint/format, small pure functions
  in ingestion/ so they're unit-testable without external services.

## Commands

```bash
bash scripts/setup_native.sh                                # one-time native setup (venvs + models)
bash scripts/run_native.sh                                  # start stack natively
bash scripts/stop_native.sh                                 # stop the native stack
bash scripts/setup_models.sh                                # pull all models
bash scripts/healthcheck.sh                                 # smoke test
python scripts/make_synthetic_data.py                       # regenerate fake docs
bash scripts/ingest.sh data/synthetic                       # index synthetic corpus
bash scripts/ingest.sh data/glossary                        # index the glossary
pytest tests/ -x -q                                         # unit tests (no services needed)
python eval/run_ragas.py                                    # RAG quality metrics (native: stop the API first — embedded Qdrant is single-process)
ruff check app/ && ruff format app/                         # lint + format
```

## Environment notes

- Dev happens on a personal laptop; deployment is `git clone` + `.env` +
  `scripts/setup_native.sh` / `run_native.sh` on a company laptop by the manager.
  Anything machine-specific belongs in
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
