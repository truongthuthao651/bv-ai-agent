---
name: insurance-rag-pipeline
description: Development guide for the local Vietnamese insurance RAG assistant. Use this skill whenever working on ANY part of this repo — document parsing (PDF/DOCX/XLSX/images), OCR, math/LaTeX equation extraction, actuarial notation, figure/chart handling, the glossary, chunking, embeddings, Qdrant indexing or retrieval, reranking, prompts, the FastAPI endpoints, Docker Compose services, ingestion scripts, evaluation, or synthetic test data. Also use it when debugging retrieval quality, adding a new document type, changing models in .env, or preparing the handover/deployment — even if the user doesn't mention "RAG" explicitly.
---

# Insurance RAG Pipeline — Development Skill

This repo is a fully-local RAG assistant for a Vietnamese life insurance firm
whose documents are math-heavy (actuarial formulas, notation, charts).
Read `CLAUDE.md` first for architecture, structure, and the security rules.
This skill covers HOW to implement and modify each stage correctly.

## Golden rules (repeat of the critical ones)

- Develop and test ONLY against `data/synthetic/`. `data/real/` is off-limits, always.
  Textbook actuarial formulas/terminology are public knowledge and fine to use.
- No network calls at runtime; the app must work air-gapped.
- Canonical format everywhere: **Markdown + LaTeX** (`$...$`, `$$...$$`).
- All Vietnamese text is NFC-normalized at ingestion. All config goes through
  `app/config/settings.py`.

## Stage-by-stage guide

### 1. Parsing (app/ingestion/parsers/)

Every parser returns the same intermediate format:

```python
@dataclass
class ParsedDocument:
    doc_title: str
    doc_type: str                  # "policy" | "procedure" | "form" | "spreadsheet" | "image" | "figure" | "glossary" | "other"
    sections: list[ParsedSection]  # ordered
    figures: list[ParsedFigure]    # extracted chart/diagram images

@dataclass
class ParsedSection:
    section_path: str   # e.g. "Chương II > Điều 5 > Khoản 2"
    text: str           # Markdown + LaTeX; tables stay as Markdown tables
    page: int | None

@dataclass
class ParsedFigure:
    image_path: str     # saved under the doc's asset folder
    page: int | None
    caption: str | None # original caption text if present
```

Rules:
- **PDF:** Docling with `do_formula_enrichment=True` so formulas come out as LaTeX.
  If the text layer is empty/garbage (< ~20 chars/page average), route to `ocr.py`
  (PaddleOCR, `lang="vi"`). Never silently return empty text. Extract figure
  regions via `figure_extract.py` and save the images.
- **DOCX:** route through **pandoc** (`-t gfm+tex_math_dollars`) so Word OMML
  equations become LaTeX — `python-docx` silently DROPS equations; never use it
  as the primary DOCX text path.
- **Scans/images with math:** normal OCR first; regions with low confidence or
  math-like symbol density go to `formula_ocr.py` (PP-FormulaNet via PaddleOCR
  PP-StructureV3, or Qwen2.5-VL prompted to transcribe formulas as LaTeX).
- **Actuarial notation warning:** pre-subscripts and annuity/insurance symbols
  (`{}_np_x`, `\ddot{a}_x`, `A_{x:\overline{n}|}`, commutation `D_x, N_x, M_x`)
  are frequently mangled by OCR/VLMs (`{}_np_x` → `np_x` is a DIFFERENT quantity).
  Cross-check extracted symbols against `data/glossary/thuat_ngu.yaml`; tag
  low-confidence formula chunks with `needs_review: true` in the payload.
- **XLSX:** one Markdown table per sheet. If a sheet exceeds the chunk budget,
  split by row groups and REPEAT the header row in every group. Forward-fill
  merged cells. Ingest computed values, not formulas.
- New document type? Add a parser returning `ParsedDocument`, register it in
  `router.py` by MIME/extension, add a fixture in `tests/fixtures/` and a test.

### 2. Enrichment (app/ingestion/enrichment.py) — runs after parsing, before chunk indexing

Embeddings match prose, not LaTeX, so every chunk gets two texts:

- `display_text`: the clean Markdown+LaTeX (goes into generation context / UI)
- `embed_text`: `"Tài liệu: {doc_title} > {section_path}\n\n"` + display_text +
  Vietnamese verbalizations

Enrichment steps:
- **Formulas:** for each chunk containing `$...$`/`$$...$$`, call the local LLM to
  produce a 1–2 sentence Vietnamese description of what each formula computes;
  append to `embed_text` only.
- **Figures:** for each `ParsedFigure`, call Qwen2.5-VL with a structured prompt:
  chart type, axes + units, series, trend, labeled key values (as a Markdown table
  if readable), in Vietnamese; instruct it to mark unlabeled readings as
  approximate ("khoảng"). Index the description as its own chunk with
  `doc_type: "figure"` and `figure_image_path` in the payload.
- Enrichment is offline batch work — it is allowed to be slow. NEVER move it to
  query time.

### 3. Chunking (app/ingestion/chunking.py)

- Split on document structure first: headings and Vietnamese legal hierarchy
  markers — `Chương`, `Mục`, `Điều`, `Khoản`, `Điểm`, plus numbered headings (`1.`, `1.1`).
- Then recursive split to 500–800 tokens with 10–15% overlap (token count via the
  embedding tokenizer, not len()).
- **Equation rules (hard constraints):**
  - Never split inside `$...$` or `$$...$$`.
  - A display equation stays in the same chunk as the paragraph immediately
    before it AND any "trong đó: ..." definition list after it.
  - If that unit exceeds the budget, the unit becomes its own oversized chunk —
    correctness beats budget here.
- Never split a Markdown table mid-row; oversized tables split by row groups with
  header repeated.

### 4. Glossary (data/glossary/thuat_ngu.yaml)

Committed to the repo (public textbook terminology only). Schema:

```yaml
- term: "phí thuần"
  synonyms: ["net premium", "phí rủi ro thuần"]
  symbol: "P"
  definition: "..."
```

Used in three places — keep them in sync when editing the schema:
1. `retrieval/query_expansion.py`: dictionary-based synonym expansion of the user
   query before hybrid search (no LLM call — must stay fast).
2. Indexed as a document (`doc_type: "glossary"`), so definition questions hit
   authoritative entries. Re-run `scripts/ingest.sh data/glossary` after edits.
3. Notation repair in parsing (see actuarial notation warning above).

When a pilot query fails due to unknown terminology, the fix is usually a new
glossary entry, not a retrieval-parameter change. Add the term + synonyms first.

### 5. Indexing & retrieval (indexer.py, retriever.py)

- bge-m3 produces dense + sparse vectors from `embed_text`; store both in one
  Qdrant collection (named vectors `dense` / `sparse`). Payload fields are listed
  in CLAUDE.md — keep them in sync with `schemas.py`.
- Query flow: glossary expansion → rewrite → hybrid search (top-20 each, RRF fuse)
  → rerank to top-5 → generation. Don't change top-k values in code; they're settings.
- Deleting/re-ingesting a document: delete by `doc_id` filter first, then upsert
  (idempotent ingestion). Delete also removes the doc's saved figure images.

### 6. Generation (prompts.py, generator.py)

- Context assembly uses `display_text`, numbered (`[1] Tài liệu: ...`) so
  citations are checkable. LaTeX passes through untouched — Open WebUI renders it
  with KaTeX.
- System prompt is Vietnamese and MUST keep four properties:
  1. Answer only from provided context.
  2. Cite sources as `[Tên tài liệu, mục X]`.
  3. Refuse gracefully with "Tôi không tìm thấy thông tin trong tài liệu" when
     context is insufficient.
  4. **Math answers:** present the relevant formula in LaTeX, show substitution
     steps if asked to compute, and ALWAYS append that numeric results must be
     verified with official tools ("Kết quả cần được kiểm tra lại bằng công cụ
     tính phí chính thức") — a local 7B model's arithmetic is not trustworthy for
     insurance calculations.
  Any prompt edit must preserve all four.
- Stream via SSE in OpenAI format so Open WebUI works unmodified.

### 7. Synthetic data & evaluation

- `scripts/make_synthetic_data.py` generates fake Vietnamese insurance documents:
  policies with Điều/Khoản structure, a claims XLSX, a scanned-form image, AND
  math-heavy samples — actuarial formulas (life contingencies: annuities,
  net premiums, reserves), a DOCX with OMML equations, and chart images. All
  names, policy numbers, and amounts are invented; formulas are textbook-standard.
- `eval/golden_set.jsonl` must include: definition questions (glossary),
  "which formula applies to X" questions, notation questions, and figure questions
  — alongside ordinary policy Q&A. When adding a synthetic doc, add 3–5 matching
  Q/A pairs.
- After any change to parsing/enrichment/chunking/retrieval: re-ingest
  `data/synthetic/`, run `pytest`, then `python eval/run_ragas.py`. Faithfulness
  or context precision dropping is a regression — investigate before merging.

## Definition of done for any change

1. `ruff check` and `pytest` pass locally (no Docker needed for unit tests).
2. If the pipeline changed: RAGAS metrics on the golden set did not regress —
   including the math/figure/glossary subsets.
3. No new hardcoded config, paths, model names, or URLs — everything via settings.
4. Equations still render in the UI (spot-check one formula answer end-to-end).
5. `.env.example` and README deployment steps updated if setup changed.
6. Nothing under `data/` (except `glossary/`), no secrets, no real-looking PII
   anywhere in the diff.
