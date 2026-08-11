# Teammate Guide — BV AI Agent

Practical guide for developers working on this codebase. For installation and URLs, see [README.md](README.md).

---

## Architecture

```
Browser → FastAPI :8000 → Ollama :11434
              ↓
       Qdrant (embedded in API process, native mode)
              ↓
       ./models/  (bge-m3, reranker, docling weights)
```

**Two pipelines:**

| Pipeline | When | Flow |
|----------|------|------|
| **Ingestion** | Admin upload / batch script | file → parse → clean → chunk → embed → Qdrant |
| **Query** | Every chat message | rewrite → expand → hybrid search → rerank → LLM → answer + citations |

Query entry point: `app/api/chat.py` → `_retrieve()` → `app/generation/generator.py`.

All parsers converge to **Markdown + LaTeX** (`$...$` inline, `$$...$$` display). Chunking, embedding, and generation only use this format.

---

## Project structure

```text
bv-ai-agent/
├── app/                      # FastAPI backend
│   ├── main.py               # Entry, auth gate, static mounts
│   ├── auth.py, accounts.py  # Session + RBAC
│   ├── config/settings.py    # All config from .env
│   ├── api/                  # chat, ingest, login, metrics, admin_ops, …
│   ├── ingestion/            # Parsers, chunking, indexing
│   ├── retrieval/            # Search, rerank, guards, query rewrite
│   ├── generation/           # Prompts, streaming, citations
│   └── static/dist/          # Committed React build (deployment serves this)
├── frontend/                 # React source — dev machine only
│   └── src/{chat,admin,landing,components,tokens}/
├── scripts/                  # setup_native.sh, run_native.sh, ingest.sh, check.sh
├── tests/                    # pytest (498 tests, no services required)
├── eval/                     # Golden-set evaluation (needs running stack)
├── data/
│   ├── glossary/             # Committed terminology
│   ├── synthetic/            # Dev/test docs ONLY
│   └── real/                 # ⛔ NEVER touch
├── requirements*.txt         # Split deps — see "Dependencies" below
```

### Where to make changes

| Task | Start here |
|------|------------|
| Answer quality / prompts | `app/generation/prompts.py` |
| Retrieval / search | `app/retrieval/` |
| Document ingestion | `app/ingestion/` |
| Chat UI | `frontend/src/chat/` |
| Admin UI | `frontend/src/admin/` |
| Auth / accounts | `app/auth.py`, `app/accounts.py`, `app/api/login.py` |
| Config | `.env.example` → `app/config/settings.py` |
| UI tokens / components | `frontend/src/tokens/`, `frontend/src/components/` |

---

## Development workflow

```bash
cp .env.example .env
bash scripts/setup_native.sh     # first time only
bash scripts/run_native.sh       # start stack
bash scripts/check.sh            # ruff + pytest before committing
cd frontend && npm run build     # after frontend changes → commit app/static/dist/
```

**Eval** (needs Ollama + ingested data): stop the API first in native mode — embedded Qdrant is single-process.

```bash
bash scripts/stop_native.sh
PY=.venv/Scripts/python.exe; [[ -x .venv/bin/python ]] && PY=.venv/bin/python
"$PY" eval/run_ragas.py --retrieval-only
```

**Test data:**

```bash
PY=.venv/Scripts/python.exe; [[ -x .venv/bin/python ]] && PY=.venv/bin/python
"$PY" scripts/make_synthetic_data.py
bash scripts/ingest.sh data/glossary
bash scripts/ingest.sh data/synthetic
```

---

## Conventions

- **Config:** every tunable value through `app/config/settings.py` — never `os.getenv()` elsewhere
- **User-facing strings:** Vietnamese · **Code/comments/commits:** English
- **Vietnamese text:** NFC-normalize on ingest
- **Versions:** pin everything in `requirements*.txt`; never use `:latest`
- **Style:** type hints, `ruff` for lint/format, small testable functions in `app/ingestion/`

### Answering rules (do not weaken in `prompts.py`)

- Answer only from retrieved context; cite as `[n]` matching the sources block
- Insufficient context → `"Tôi không tìm thấy thông tin trong tài liệu."`
- Calculations → show formula + append disclaimer: *"Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức."*
- Never invert exclusion clauses; never remap table metrics (lãi suất cam kết ≠ tỷ lệ bồi thường)
- Coverage questions → enumerate cases with citations, not a single flat verdict

---

## Security (non-negotiable)

1. **Never** read, list, or reference `data/real/`
2. Dev and tests use `data/synthetic/` only
3. No external API calls at runtime — fully air-gapped after setup
4. Do not commit `.env`, `models/`, `qdrant_storage/`, or runtime DBs under `data/`
5. Exception: `data/glossary/` is committed (public terminology only)
6. No telemetry or analytics

Knowledge-pack URLs in citations are **rendered only** — never fetched at runtime.

---

## Dependencies

Four requirement files — **do not merge**; install order matters (CPU torch before FlagEmbedding/docling):

```bash
pip install -r requirements.txt
pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-embed.txt
pip install torchvision==0.27.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-pdf.txt
# requirements-ml.txt (PaddleOCR, ragas) — deferred, not in setup_native.sh
```

`scripts/setup_native.sh` runs this sequence automatically.

---

## Build & deployment

| Mode | Notes |
|------|-------|
| **Native (production)** | Python + Ollama only; serves committed `app/static/dist/` |
| **Frontend rebuild** | `cd frontend && npm install && npm run build` — commit output |

Embedded Qdrant (`QDRANT_LOCAL_PATH`) is single-process: stop the API before running `eval/run_ragas.py` natively.

---

## Testing

```bash
bash scripts/check.sh              # full check (ruff + pytest)
cd frontend && npm run lint        # oxlint (after npm run prelint)
```

Key test modules: `test_parsers.py`, `test_chunking.py`, `test_retrieval.py`, `test_generation.py`, `test_ingest.py`, `test_auth.py`.

Pre-commit hook (optional): `pre-commit install` runs `scripts/check.sh`.

---

## Gotchas

| Issue | Cause / fix |
|-------|-------------|
| First answer very slow | Cold model — enable `WARMUP_ON_STARTUP=true`; check `OLLAMA_KEEP_ALIVE` |
| `/health` qdrant error | Embedded storage locked by another process — stop duplicate API/eval |
| Citation links dead on LAN | Set `API_PUBLIC_BASE_URL` to server LAN IP |
| Wrong refusals | Re-ingest; tune `RERANK_MIN_SCORE`; check `logs/api.log` |
| Ingest PDF fails | Run `bash scripts/setup_models.sh` (Docling weights) |
| `LLM_THINKING=true` | Very slow on CPU — keep **`false`** |

Latency breakdown: `grep -i timing logs/api.log`

---

## Current status

Verified against the codebase and test suite (498 passing tests).

### Core platform

- [x] FastAPI backend with OpenAI-compatible `/v1/chat/completions` (SSE streaming)
- [x] Embedded Qdrant (native, single-process)
- [x] Native deployment scripts (`setup_native.sh`, `run_native.sh`, `stop_native.sh`)
- [x] Config via pydantic-settings (`.env` → `settings.py`)
- [x] Health check, query timing logs, metrics summary endpoint

### Ingestion

- [x] Markdown, DOCX (pandoc), XLSX, PDF (Docling + formula enrichment), glossary YAML
- [x] Equation-safe chunking, formula verbalization, hybrid bge-m3 indexing
- [x] Admin upload/edit/delete via `/admin` and `POST /ingest`
- [x] Knowledge pack script for offline public references
- [ ] Scanned image / OCR ingestion (stubs exist; router raises `NotImplementedError`)

### Retrieval & generation

- [x] Glossary query expansion, LLM query rewrite, conversation scope
- [x] Hybrid dense + sparse search, RRF fusion, bge-reranker reranking
- [x] Spellcheck gate, product scope, comparison mode, metric guard, coverage guards
- [x] Vietnamese prompts with citations, refusal, math disclaimer, advisory mode
- [x] Coverage gate + verification pass for benefit-clause answers

### Frontend

- [x] React app: landing (`/`), chat (`/chat`), admin (`/admin`) — single port
- [x] KaTeX math, citation source panel, prompt suggestions
- [x] Chat: streaming, cancel, loading indicator, session persistence, feedback thumbs-down
- [x] Admin: overview dashboard, documents CRUD + search, users list, config/logs/eval views
- [x] RBAC enforced server-side; password change in UI
- [x] Responsive admin layout (mobile drawer)

### Auth & accounts

- [x] Email `@baoviet.com.vn` + password (PBKDF2, SQLite)
- [x] Admin provisioning via `scripts/seed_accounts.py`
- [x] Employee self-registration at `/login`
- [x] Session-protected document view/file routes

### Quality & ops

- [x] 498 unit tests; `scripts/check.sh` (ruff + pytest)
- [x] Golden-set eval harness (`eval/run_ragas.py`)
- [x] Pre-commit config for `check.sh`
- [ ] Frontend automated tests
- [ ] `npm run lint` in `check.sh`

---

## Future improvements

### High priority

- [ ] End-to-end OCR for scanned PDFs and images (PaddleOCR + formula OCR — `requirements-ml.txt` slice)
- [ ] Reduce reranker latency on CPU-only machines
- [ ] Frontend test suite (`markdown.jsx`, SSE parsing, theme hook)
- [ ] Wire `npm run lint` into `scripts/check.sh`

### Medium priority

- [ ] Extract query pipeline from `app/api/chat.py` into `app/generation/pipeline.py`
- [ ] Fix refusal-mode mislabeling in query timing logs (`mode="refusal"` when answer is a refusal)
- [ ] Thread `first_token_ms` through all generator logging paths
- [ ] Modal focus trap and focus return (accessibility)
- [ ] `aria-live` region for streaming answers (screen reader support)
- [ ] Server-side document pagination when corpus exceeds a few hundred docs
- [ ] Rate limiting on `POST /login`
- [ ] Broaden golden set `calculation` category coverage

### Nice to have

- [ ] Account deactivation / admin password reset flow
- [ ] Zip-bomb / decompression-ratio guard on DOCX/XLSX uploads
- [ ] Query timing log rotation policy
- [ ] TLS deployment guide for LAN (reverse proxy)
- [ ] Command palette (⌘K) in admin — currently visual affordance only

---

## Query flow example

**User:** *"Net premium khác gross premium chỗ nào?"*

1. `query_rewrite.py` — standalone question from chat history
2. `query_expansion.py` — glossary adds `phí thuần`, `phí gộp`
3. `retriever.py` — hybrid search → RRF fusion
4. `reranker.py` — cross-encoder → top-5 chunks
5. `generator.py` — Vietnamese answer with `[n]` citations + "Nguồn tham khảo" block

---

*Last updated: 2026-08-09*
