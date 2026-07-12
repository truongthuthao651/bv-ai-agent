# Hướng dẫn cho teammate — Trợ lý AI Bảo Việt Life (Local RAG)

> **Teammate guide — Local Vietnamese Insurance RAG Assistant**
>
> Tài liệu này giúp bạn (biết code nhưng chưa từng làm chatbot) hiểu **hệ thống
> đang làm gì**, **tại sao thiết kế như vậy**, và **chạy demo / test từ A→Z**.
> Mỗi phần có giải thích **tiếng Việt dễ hiểu** trước, rồi **English / technical
> detail** ngay sau.

---

## Mục lục / Table of contents

1. [Ý tưởng lớn — Chatbot này khác ChatGPT thế nào?](#1-ý-tưởng-lớn)
2. [RAG là gì? (non-technical)](#2-rag-là-gì)
3. [Kiến trúc tổng quan & công nghệ](#3-kiến-trúc--công-nghệ)
4. [Cấu trúc thư mục dự án](#4-cấu-trúc-thư-mục)
5. [Hai pipeline chính: Nạp tài liệu & Trả lời câu hỏi](#5-hai-pipeline)
6. [Chi tiết từng giai đoạn (ingestion)](#6-ingestion-chi-tiết)
7. [Chi tiết từng giai đoạn (query / chat)](#7-query-chi-tiết)
8. [Quy tắc bảo mật (bắt buộc)](#8-bảo-mật)
9. [Chạy demo end-to-end (command line)](#9-demo-end-to-end)
10. [Testing & đánh giá chất lượng](#10-testing)
11. [Cấu hình quan trọng (`.env`)](#11-cấu-hình)
12. [Troubleshooting thường gặp](#12-troubleshooting)
13. [Bạn nên đọc file nào tiếp?](#13-đọc-tiếp)

---

## 1. Ý tưởng lớn

### Tiếng Việt (dễ hiểu)

Công ty bảo hiểm có rất nhiều tài liệu: hợp đồng, quy trình, bảng tính, công thức
định phí. Nhân viên muốn hỏi kiểu ChatGPT:

> *"Phí thuần là gì?"* · *"Công thức tính dự phòng nghiệp vụ?"* · *"Điều 5 nói gì?"*

Nhưng **không được** đưa tài liệu công ty lên ChatGPT / Claude / Gemini (mật,
offline). Vì vậy chúng ta tự dựng một chatbot **chạy 100% trên máy nội bộ**:

| Yêu cầu | Cách giải quyết |
|--------|------------------|
| Không lộ dữ liệu ra ngoài | Không gọi API cloud; mọi model chạy local qua Ollama |
| Trả lời đúng theo tài liệu, không bịa | Dùng **RAG** — tìm đoạn văn liên quan rồi mới trả lời |
| Có nguồn trích dẫn | Mỗi câu trả lời kèm `[Tên tài liệu, mục X]` |
| Hiển thị công thức toán đẹp | Lưu công thức dạng LaTeX; Open WebUI render bằng KaTeX |
| Máy yếu vẫn chạy được | Đổi model trong `.env` (vd. `qwen3:4b`) — không sửa code |

### English (technical)

This is an **air-gapped, OpenAI-compatible RAG API** (FastAPI) + **Open WebUI**
frontend. Chat / vision models are served by **Ollama**; embeddings + reranker
use **FlagEmbedding** weights on disk; vectors live in **Qdrant** (hybrid dense
+ sparse). The public surface is `POST /v1/chat/completions` (SSE), so any
OpenAI-compatible client works without custom SDKs.

---

## 2. RAG là gì?

### Non-technical — so sánh với "LLM thuần"

```
❌ LLM thuần (như ChatGPT không có tài liệu của bạn):
   Câu hỏi → Model đoán dựa trên kiến thức đã train → Có thể bịa

✅ RAG (Retrieval-Augmented Generation) — cách hệ thống này hoạt động:
   Câu hỏi
      → Tìm vài đoạn tài liệu liên quan nhất (Retrieval)
      → Đưa đoạn đó + câu hỏi vào model (Augmented)
      → Model chỉ được phép trả lời dựa trên đoạn đó (Generation)
```

**Hình dung:** Bạn không nhờ một người "nhớ hết sách bảo hiểm", mà nhờ thư viện
viên **mở đúng trang**, đưa trang đó cho chuyên gia đọc, rồi chuyên gia trả lời
và ghi rõ "theo trang nào".

Hai khái niệm then chốt:

1. **Ingestion (nạp tài liệu)** — làm offline / batch: đọc file → cắt nhỏ →
   tạo vector → lưu vào Qdrant. Chậm cũng được.
2. **Query (hỏi đáp)** — làm realtime: nhận câu hỏi → tìm vector gần nhất →
   xếp hạng lại → gọi LLM stream câu trả lời.

### Technical — vocabulary cheat sheet

| Term | Nghĩa ngắn | Trong repo này |
|------|------------|----------------|
| **Embedding / vector** | Số hóa ý nghĩa của đoạn văn thành mảng số | `bge-m3` → dense 1024-d + sparse |
| **Chunk** | Một "miếng" tài liệu đủ nhỏ để retrieve | ~500–800 tokens, không cắt giữa công thức |
| **Vector DB** | Database chuyên tìm "đoạn gần nghĩa nhất" | Qdrant collection `insurance_docs` |
| **Hybrid search** | Kết hợp tìm theo nghĩa (dense) + từ khóa (sparse) | RRF fusion |
| **Reranker** | Model xếp lại top kết quả cho chính xác hơn | `bge-reranker-v2-m3` → top-5 |
| **Grounding / citation** | Buộc trả lời dựa trên context + ghi nguồn | `prompts.py` + sources block |
| **SSE streaming** | Trả lời từng token realtime như ChatGPT | OpenAI-compatible SSE |

---

## 3. Kiến trúc & công nghệ

### Sơ đồ tổng quan

```
┌─────────────┐     OpenAI-compatible      ┌──────────────────┐
│ Open WebUI  │ ──────────────────────────►│  FastAPI (api)   │
│ :3000       │   /v1/chat/completions     │  :8000           │
│ (chat UI)   │◄──── SSE tokens ───────────│                  │
└─────────────┘                            │  ingest / health │
                                           └────────┬─────────┘
                    ┌───────────────────────────────┼───────────────────────────────┐
                    ▼                               ▼                               ▼
             ┌────────────┐                  ┌────────────┐                  ┌────────────┐
             │  Ollama    │                  │   Qdrant   │                  │ ./models   │
             │  :11434    │                  │   :6333    │                  │ (HF weights│
             │ chat+vision│                  │ vectors    │                  │ embed/rerank│
             └────────────┘                  └────────────┘                  └────────────┘
```

Admin UI tuỳ chọn: `http://localhost:8000` (upload / health / hỏi thử nhanh).
User hàng ngày chủ yếu dùng Open WebUI `:3000`.

### Stack chi tiết (tools & technologies)

| Lớp | Công nghệ | Vai trò | Ghi chú |
|-----|-----------|---------|---------|
| **Orchestration** | Docker Compose | Chạy 4 service: ollama, qdrant, api, open-webui | Tag pinned, không dùng `:latest` |
| **API** | FastAPI + Uvicorn | HTTP API, SSE streaming, lifespan warmup | `app/main.py` |
| **Config** | pydantic-settings | Mọi biến đọc từ `.env` qua `settings.py` | Không `os.getenv()` lung tung |
| **Chat LLM** | Ollama + Qwen3 (`qwen3:8b`) | Sinh câu trả lời tiếng Việt | Máy yếu: `qwen3:4b` |
| **Vision LLM** | Ollama + Qwen2.5-VL (`qwen2.5vl:7b`) | Mô tả biểu đồ / OCR công thức (enrichment) | Chậm — chỉ lúc ingest |
| **Embeddings** | FlagEmbedding `bge-m3` | Dense + sparse vectors | **Không** qua Ollama (Ollama không đủ sparse) |
| **Reranker** | `bge-reranker-v2-m3` | Cross-encoder xếp lại top hits | Có sàn điểm `RERANK_MIN_SCORE` |
| **Vector DB** | Qdrant v1.12.4 | Named vectors `dense` / `sparse` | Telemetry tắt |
| **PDF parse** | Docling (`do_formula_enrichment`) | PDF → Markdown + LaTeX | Weights trong `./models/docling` |
| **DOCX parse** | pandoc (`gfm+tex_math_dollars`) | Word OMML → LaTeX | **Không** dùng `python-docx` làm path chính (nó drop equation) |
| **XLSX** | pandas / openpyxl | Sheet → Markdown table | Header lặp lại mỗi chunk |
| **OCR (WIP)** | PaddleOCR `lang=vi` + formula OCR | Scan / ảnh | Chưa bật end-to-end — image parser raise `NotImplementedError` |
| **Frontend** | Open WebUI 0.5.4 | Chat UI, KaTeX cho LaTeX | Trỏ `OPENAI_API_BASE_URL` vào FastAPI |
| **Upload từ UI** | Open WebUI Pipe (`ingest_pipe.py`) | Model giả "📥 Nạp tài liệu" → `POST /ingest` | Setup 1 lần (admin) |
| **Eval** | `eval/run_ragas.py` + golden set | Hit rate, faithfulness, refusal, citation | Offline, không phụ thuộc package `ragas` |
| **Lint / test** | ruff, pytest | Unit test không cần Docker | `tests/` dùng fixture synthetic |

### Canonical format (định dạng chuẩn duy nhất)

**Tất cả** parser đều hội tụ về:

```text
Markdown + LaTeX math
  - inline:  $P = \ldots$
  - display: $$ \ddot{a}_x = \ldots $$
```

Chunking, embedding, UI **chỉ** làm việc với format này. Không giữ HTML / Word
XML / raw PDF bytes trong retrieval path.

---

## 4. Cấu trúc thư mục

```text
bv-ai-agent/
├── README.md                 # Deploy cho manager (VI trước)
├── CLAUDE.md                 # Architecture + security rules (cho AI/dev)
├── docs/TEAMMATE_GUIDE.md    # ← bạn đang đọc
├── .env.example → copy thành .env trên mỗi máy
├── docker-compose.yml        # CPU baseline
├── docker-compose.gpu.yml    # Override NVIDIA cho ollama
├── Dockerfile                # Image FastAPI (python:3.12-slim + pandoc)
├── requirements*.txt         # Pinned deps
│
├── app/                      # Toàn bộ backend
│   ├── main.py               # FastAPI entry + warmup + admin static UI
│   ├── config/settings.py    # SINGLE source of config
│   ├── api/
│   │   ├── chat.py           # POST /v1/chat/completions (+ GET /v1/models)
│   │   ├── ingest.py         # POST /ingest, GET/DELETE /documents
│   │   └── health.py         # GET /health
│   ├── ingestion/            # Nạp tài liệu
│   │   ├── router.py         # Extension → parser
│   │   ├── parsers/          # pdf, docx, xlsx, glossary, (image WIP)
│   │   ├── cleaning.py       # NFC normalize, strip header/footer
│   │   ├── chunking.py       # Heading-aware, never-split-equation
│   │   ├── enrichment.py     # Verbalize formulas + describe figures
│   │   └── indexer.py        # bge-m3 → Qdrant upsert
│   ├── retrieval/
│   │   ├── query_rewrite.py  # Chat history → standalone question
│   │   ├── query_expansion.py# Glossary synonyms (no LLM)
│   │   ├── retriever.py      # Hybrid search + RRF
│   │   └── reranker.py       # bge-reranker → top-k + min score
│   ├── generation/
│   │   ├── prompts.py        # System prompt VI + citation rules
│   │   └── generator.py      # Ollama call, stream, calc disclaimer
│   ├── models/schemas.py     # Pydantic models
│   └── static/               # Admin UI (optional)
│
├── scripts/
│   ├── setup_models.sh       # ollama pull + HF download
│   ├── healthcheck.sh        # Smoke test 4 services
│   ├── ingest.sh             # Batch POST /ingest một folder
│   ├── make_synthetic_data.py
│   └── open_webui/           # Pipe "Nạp tài liệu" + README setup
│
├── data/                     # GITIGNORED (trừ glossary/)
│   ├── glossary/thuat_ngu.yaml   # Thuật ngữ công khai — ĐƯỢC commit
│   ├── synthetic/            # Fake docs — CHỈ dùng cái này khi dev/test
│   └── real/                 # ⛔ CẤM đụng — tài liệu thật trên máy công ty
│
├── eval/
│   ├── golden_set.jsonl      # Q/A chuẩn (glossary, formula, policy, …)
│   └── run_ragas.py          # Chạy metric offline
│
└── tests/                    # Unit tests + fixtures nhỏ
```

### Convention nhanh

- **User-facing strings / prompts:** tiếng Việt  
- **Code, comments, commit messages:** English  
- **Config:** luôn qua `from app.config.settings import settings`  
- **Vietnamese text:** luôn NFC-normalize lúc ingest  

---

## 5. Hai pipeline

### 5.1 Ingestion — "đưa sách vào thư viện"

```text
File (PDF/DOCX/XLSX/MD/YAML)
    │
    ▼
router.py ──► parser phù hợp ──► ParsedDocument (Markdown + LaTeX)
    │
    ▼
cleaning.py ──► Unicode NFC, bỏ header/footer rác
    │
    ▼
chunking.py ──► cắt theo Chương/Điều/Khoản…; KHÔNG cắt giữa $...$
    │
    ▼
enrichment.py ──► (optional) LLM mô tả công thức bằng tiếng Việt
                 ──► (optional) VLM mô tả biểu đồ
    │              mỗi chunk có:
    │                display_text  = Markdown sạch (đưa vào LLM lúc trả lời)
    │                embed_text    = prefix tài liệu + display + verbalization
    ▼
indexer.py ──► bge-m3 (dense+sparse) ──► Qdrant upsert
```

**Tại sao có 2 text?** Embedding giỏi với **văn xuôi**, kém với **ký hiệu LaTeX
thuần**. Verbalization ("Công thức này tính phí thuần …") giúp tìm đúng đoạn
khi user hỏi bằng lời thường.

### 5.2 Query — "hỏi thư viện viên"

```text
User message (Open WebUI / curl)
    │
    ▼
query_rewrite.py     # "cái đó là bao nhiêu?" + history → câu hỏi đứng độc lập
    │
    ▼
query_expansion.py   # "net premium" → thêm "phí thuần" (từ glossary, không gọi LLM)
    │
    ▼
hybrid_search        # dense top-20 + sparse top-20 → RRF fusion
    │
    ▼
rerank               # cross-encoder → top-5; drop nếu score < RERANK_MIN_SCORE
    │                  nếu không còn hit → trả REFUSAL ngay (không gọi LLM đoán)
    ▼
generator            # system prompt VI + context [1][2]… + câu hỏi
    │                  stream SSE; append "Nguồn tham khảo";
    │                  nếu có số liệu tính toán → đảm bảo có disclaimer kiểm tra
    ▼
Open WebUI hiển thị (KaTeX render $...$)
```

Code path chính: `app/api/chat.py` → `_retrieve()` → `generator`.

---

## 6. Ingestion chi tiết

### 6.1 Parsing theo loại file

| Extension | Parser | Điểm quan trọng |
|-----------|--------|-----------------|
| `.md` / `.markdown` | markdown parser | Đã gần canonical format |
| `.docx` | pandoc → `gfm+tex_math_dollars` | Giữ OMML equations thành LaTeX |
| `.xlsx` | pandas → Markdown table | Forward-fill merged cells; lặp header khi split |
| `.pdf` | Docling + formula enrichment | Text layer rỗng → sẽ route OCR (khi OCR sẵn sàng) |
| `.yaml` / `.yml` | glossary parser | Index từng term như một chunk `doc_type=glossary` |
| `.png` / `.jpg` | *(WIP)* | Hiện `NotImplementedError` |

### 6.2 Chunking — quy tắc cứng với công thức

- Ưu tiên cắt theo cấu trúc pháp lý VN: `Chương`, `Mục`, `Điều`, `Khoản`, `Điểm`.
- Sau đó recursive split ~500–800 tokens, overlap ~12%.
- **Không bao giờ** cắt bên trong `$...$` / `$$...$$`.
- Display equation phải đi kèm đoạn "trong đó: …" định nghĩa biến.
- Nếu unit quá lớn → chấp nhận chunk oversized (đúng quan trọng hơn budget).

### 6.3 Glossary (`data/glossary/thuat_ngu.yaml`)

Chỉ chứa thuật ngữ **công khai / textbook**. Dùng ở 3 chỗ:

1. **Query expansion** — mở rộng synonym trước khi search  
2. **Indexed document** — câu hỏi định nghĩa hit đúng entry  
3. **Notation repair** (khi OCR) — đối chiếu `{}_np_x` vs `np_x` (khác nghĩa!)

Sau khi sửa glossary: `bash scripts/ingest.sh data/glossary`.

### 6.4 Payload lưu trong Qdrant (metadata)

Mỗi point roughly có: `doc_id`, `doc_title`, `section_path`, `page`,
`department`, `doc_type`, `figure_image_path?`, `ingested_at`, cộng
`display_text` / fields cần cho generation.

`doc_type ∈ {policy, procedure, form, spreadsheet, image, figure, glossary, other}`.

---

## 7. Query chi tiết

### 7.1 Bốn quy tắc trả lời (không được làm yếu trong `prompts.py`)

1. **Chỉ trả lời từ ngữ cảnh** đã retrieve — không bịa.  
2. **Trích dẫn** dạng `[Tên tài liệu, mục X]`.  
3. Không đủ thông tin → đúng câu:  
   `Tôi không tìm thấy thông tin trong tài liệu.`  
4. Có tính toán số → hiện công thức LaTeX + bước thay số + disclaimer:  
   `Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức.`  
   (Model local 7–8B **không** đáng tin cho số liệu bảo hiểm.)

Ngoài prompt, code còn có **guardrail xác định**:

- Không còn hit sau `RERANK_MIN_SCORE` → refusal ngay (không gọi LLM).  
- Answer có số liệu tính toán mà quên disclaimer → generator tự append.

### 7.2 Open WebUI meta-tasks

Open WebUI đôi khi gửi prompt kiểu "Create a concise title…" vào cùng endpoint.
`chat.py` nhận diện và **bypass RAG** (tránh tốn vài phút retrieve cho việc đặt
tên chat).

---

## 8. Bảo mật

Các quy tắc **không thương lượng**:

1. **Không đọc / list / commit / reference `data/real/`.** Dev & test chỉ dùng
   `data/synthetic/`.
2. Không đưa nội dung tài liệu thật, tên khách, số HĐ, số tiền thật vào code,
   test, log, commit message. (Công thức actuarial textbook thì OK.)
3. `data/` (trừ `glossary/`), `.env`, `models/`, `qdrant_storage/` là gitignored —
   không force-add.
4. Runtime **không** gọi API ngoài. Network chỉ lúc setup: `ollama pull`,
   `pip install`, download HF weights.
5. Không thêm telemetry / analytics.

---

## 9. Demo end-to-end (command line)

### 9.0 Prerequisites

- Docker Desktop (hoặc Docker Engine + Compose)
- ~20–40 GB trống cho models (tuỳ CHAT_MODEL)
- Git clone repo này
- (Optional) GPU NVIDIA trên Linux — xem bước GPU bên dưới  
- (Optional) Apple Silicon: xem mục "macOS Metal" — Docker **không** pass GPU Mac

### 9.1 Lần đầu — setup đầy đủ

```bash
# 0) Vào thư mục project
cd /path/to/bv-ai-agent

# 1) Tạo cấu hình máy local
cp .env.example .env
# Máy yếu: mở .env sửa  CHAT_MODEL=qwen3:4b
# (hoặc qwen3:1.7b trên Mac khi dùng Ollama native — xem 9.5)

# 2) Build & start stack (CPU)
docker compose up -d --build

#    Có GPU NVIDIA (Linux):
#    docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build

# 3) Đợi container healthy (lần đầu API warmup có thể lâu)
docker compose ps
docker compose logs -f api   # Ctrl+C khi thấy warmup xong / sẵn sàng

# 4) Tải models (CẦN mạng — chỉ bước này)
bash scripts/setup_models.sh
#    - ollama pull chat + vision
#    - download bge-m3 + reranker vào ./models
#    - download Docling PDF weights vào ./models/docling

# 5) Smoke test 4 service
bash scripts/healthcheck.sh
# Kỳ vọng: Ollama, Qdrant, FastAPI, Open WebUI đều [ OK ]
```

### 9.2 Tạo dữ liệu giả & nạp vào Qdrant

```bash
# Tạo / refresh tài liệu synthetic (fake policies, formulas, …)
# Chạy trên host nếu đã có Python deps; hoặc trong container:
docker compose exec api python scripts/make_synthetic_data.py

# Nạp glossary (thuật ngữ) — nhanh
bash scripts/ingest.sh data/glossary

# Nạp corpus synthetic — CHẬM nếu ENABLE_ENRICHMENT=true (mỗi chunk có công thức gọi LLM)
bash scripts/ingest.sh data/synthetic

# Kiểm tra danh sách document đã index
curl -s http://localhost:8000/documents | python -m json.tool
```

> Enrichment có thể mất **vài phút / file** trên CPU. Đó là bình thường — làm
> offline một lần, không phải lúc user hỏi.

### 9.3 Hỏi thử qua API (không cần UI)

```bash
# Non-streaming
curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "bao-viet-life",
    "stream": false,
    "messages": [
      {"role": "user", "content": "Phí thuần là gì?"}
    ]
  }' | python -m json.tool

# Streaming (SSE) — giống Open WebUI
curl -N http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "bao-viet-life",
    "stream": true,
    "messages": [
      {"role": "user", "content": "Công thức tính phí thuần liên quan thế nào đến dự phòng?"}
    ]
  }'
```

Câu hỏi nên refusal (off-topic):

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "bao-viet-life",
    "stream": false,
    "messages": [
      {"role": "user", "content": "Thời tiết Hà Nội hôm nay thế nào?"}
    ]
  }'
# Kỳ vọng gần đúng: "Tôi không tìm thấy thông tin trong tài liệu."
```

### 9.4 Mở giao diện

```text
Chat chính:     http://localhost:3000   (Open WebUI)
Admin (tuỳ chọn): http://localhost:8000   (upload / status / hỏi thử)
Health:         http://localhost:8000/health
Qdrant dashboard: http://localhost:6333/dashboard  (nếu bật)
```

**Nạp tài liệu từ Open WebUI** (một lần setup admin): làm theo
`scripts/open_webui/README.md` — cài Pipe function `ingest_pipe.py`, chọn model
**📥 Nạp tài liệu**, đính kèm file, gửi.

Sau đó chuyển lại model chat bình thường (`bao-viet-life` / tên trong
`ASSISTANT_NAME`) để hỏi.

### 9.5 macOS Apple Silicon — GPU Metal (khuyến nghị khi demo trên Mac)

Docker trên Mac **không** dùng được GPU. Để nhanh hơn:

```bash
# 1) Dừng Ollama trong compose (tránh giữ port 11434)
docker compose stop ollama

# 2) Chạy Ollama native (Metal)
OLLAMA_HOST=0.0.0.0:11434 ollama serve &
ollama pull qwen3:1.7b   # hoặc model bạn set trong .env

# 3) Trong .env:
#    OLLAMA_BASE_URL=http://host.docker.internal:11434
#    CHAT_MODEL=qwen3:1.7b   # khớp với model đã pull
#    LLM_THINKING=false      # rất quan trọng trên CPU/Metal nhỏ

# 4) Recreate API để nhận env mới
docker compose up -d --no-deps api
```

Deploy máy công ty Linux/NVIDIA: giữ `OLLAMA_BASE_URL=http://ollama:11434` và
dùng `docker-compose.gpu.yml`.

### 9.6 Dừng / reset

```bash
# Dừng containers (giữ volumes + qdrant_storage trên disk)
docker compose down

# Dừng + XOÁ volumes Docker (Open WebUI data, ollama volume trong Docker)
# KHÔNG xoá ./models hay ./qdrant_storage trên host trừ khi bạn chủ động xoá
docker compose down -v

# Xoá index Qdrant trên host (phải ingest lại)
# rm -rf qdrant_storage   # cẩn thận — mất toàn bộ vector đã nạp
```

### 9.7 Checklist demo 15 phút (sau khi đã setup_models một lần)

```bash
docker compose up -d
bash scripts/healthcheck.sh
bash scripts/ingest.sh data/glossary          # nếu collection trống
# mở http://localhost:3000 → hỏi "Phí thuần là gì?"
# kỳ vọng: định nghĩa tiếng Việt + citation glossary/tài liệu
```

---

## 10. Testing

### 10.1 Unit tests (không cần Docker)

Chạy trên host khi đã cài deps Python (hoặc trong container cũng được):

```bash
# Trong container (đơn giản nhất nếu chưa setup venv)
docker compose exec api pytest tests/ -x -q

# Hoặc trên host (sau khi pip install -r requirements.txt …)
pytest tests/ -x -q
```

Các file test chính:

| File | Kiểm tra gì |
|------|-------------|
| `test_parsers.py` | DOCX/MD/… → Markdown+LaTeX, OMML |
| `test_chunking.py` | Không cắt giữa equation |
| `test_enrichment.py` | Verbalization / embed vs display text |
| `test_retrieval.py` | Glossary expansion, search helpers |
| `test_generation.py` | Prompt rules, disclaimer, sources |
| `test_ingest.py` | Ingest path / doc_id |
| `test_eval.py` | Eval harness sanity |
| `test_config.py` / `test_startup.py` | Settings & app boot |

Lint:

```bash
docker compose exec api ruff check app/
# hoặc trên host:
ruff check app/ && ruff format app/
```

### 10.2 Golden-set evaluation (cần stack + đã ingest)

```bash
# Full eval (retrieval + generation + LLM-as-judge) — lâu trên CPU
docker compose exec api python eval/run_ragas.py

# Nhanh hơn — chỉ đo retrieval
docker compose exec api python eval/run_ragas.py --retrieval-only

# Lọc theo category (vd. formula)
docker compose exec api python eval/run_ragas.py --category formula --no-judge
```

Kết quả in ra terminal và ghi JSON dưới `eval/results/` (gitignored).

Metric bạn nên quan tâm:

- **Context precision / recall / MRR** — có retrieve đúng doc/section không  
- **Refusal accuracy** — câu hỏi ngoài phạm vi có từ chối đúng không  
- **Citation presence** — có trích dẫn không  
- **Faithfulness / correctness** — LLM judge (local, binary)  
- **Calc disclaimer** — câu trả lời số liệu có disclaimer không  

Hạ metric so với lần trước = regression → điều tra trước khi merge.

### 10.3 Definition of done (khi sửa code)

1. `ruff check` + `pytest` pass  
2. Nếu đụng pipeline: re-ingest synthetic + chạy eval, không regress  
3. Không hardcode URL / model / path — chỉ qua `settings`  
4. Spot-check một câu trả lời có công thức vẫn render LaTeX trên UI  
5. Cập nhật `.env.example` / README nếu đổi setup  
6. Diff không chứa `data/real/`, secrets, PII giả giống thật  

---

## 11. Cấu hình

Toàn bộ qua `.env` → `app/config/settings.py`. Một số biến hay đụng:

| Biến | Ý nghĩa | Gợi ý |
|------|---------|-------|
| `CHAT_MODEL` | Model trả lời | `qwen3:8b` / `4b` / `1.7b` |
| `LLM_THINKING` | Bật `<think>` của Qwen3 | **Giữ `false`** trừ khi debug |
| `OLLAMA_BASE_URL` | Địa chỉ Ollama | Compose: `http://ollama:11434`; Mac Metal: `http://host.docker.internal:11434` |
| `RETRIEVE_TOP_K` | Top-k mỗi nhánh dense/sparse | Default 20 |
| `RERANK_TOP_K` | Số chunk đưa vào LLM | Default 5 |
| `RERANK_MIN_SCORE` | Sàn relevance | Default `0.05` — cao quá → false refusal |
| `ENABLE_ENRICHMENT` | Verbalize lúc ingest | `true` chất lượng hơn, chậm hơn |
| `ENABLE_QUERY_EXPANSION` | Glossary synonyms | Nên `true` |
| `ENABLE_QUERY_REWRITE` | Rewrite từ history | Nên `true` |
| `WARMUP_ON_STARTUP` | Preload model lúc boot | `true` trên máy demo |
| `ASSISTANT_NAME` / `ASSISTANT_MODEL_ID` | Branding UI | Không đổi model thật |
| `CHUNK_MAX_TOKENS` | Budget chunk | Default 800 |

---

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử |
|-------------|------------------------|---------|
| `healthcheck` fail Ollama | Container chưa ready / Mac đang dùng native Ollama nhưng compose ollama cũng chạy | `docker compose logs ollama`; hoặc `stop ollama` nếu dùng native |
| Câu đầu tiên cực chậm | Cold load model | Bật `WARMUP_ON_STARTUP`; tăng `OLLAMA_KEEP_ALIVE=2h` |
| Trả lời chậm dù đã warmup | `LLM_THINKING=true` hoặc model quá lớn trên CPU | Set `LLM_THINKING=false`; giảm `CHAT_MODEL` |
| "Không tìm thấy…" cho câu hỏi đúng | Chưa ingest / `RERANK_MIN_SCORE` cao / enrichment thiếu | `curl /documents`; ingest lại; xem log `retrieval timings` |
| Ingest PDF fail / lâu | Docling weights chưa tải | Chạy lại `setup_models.sh`; lần đầu cần mạng |
| Open WebUI không thấy model | API chưa lên / `GET /v1/models` lỗi | `curl localhost:8000/v1/models`; check `OPENAI_API_BASE_URL` |
| Upload trong WebUI không vào Qdrant của ta | Dùng paperclip mặc định của WebUI (RAG nội bộ của nó) | Dùng Pipe **📥 Nạp tài liệu** (`scripts/open_webui/README.md`) |
| Equation bị mất khi parse DOCX | Ai đó dùng python-docx thay pandoc | Giữ path pandoc trong `docx_parser.py` |
| Test fail vì thiếu model | Unit test không cần Ollama; nếu test hit network | Chạy `pytest` không cần stack; integration cần compose |

Xem latency từng stage trong log API:

```bash
docker compose logs -f api | grep -i timing
```

---

## 13. Đọc tiếp

| File | Khi nào đọc |
|------|-------------|
| `README.md` | Deploy trên máy công ty / handover manager |
| `CLAUDE.md` | Architecture + security canonical |
| `.claude/skills/insurance-rag-pipeline/SKILL.md` | Guide implement từng stage (parsing → eval) |
| `scripts/open_webui/README.md` | Setup nút "Nạp tài liệu" trong UI |
| `.env.example` | Comment chi tiết từng biến |
| `app/api/chat.py` | Entry point query flow |
| `app/generation/prompts.py` | Quy tắc trả lời (đọc trước khi sửa prompt) |

---

## Phụ lục A — Thuật ngữ nội bộ (VI ↔ EN)

| Tiếng Việt | English trong code |
|------------|--------------------|
| Nạp tài liệu | Ingestion / `POST /ingest` |
| Tra cứu / tìm đoạn liên quan | Retrieval / hybrid search |
| Xếp hạng lại | Reranking |
| Sinh câu trả lời | Generation |
| Từ điển thuật ngữ | Glossary |
| Công thức / định phí | Formula / actuarial math |
| Từ chối trả lời | Refusal |
| Nguồn tham khảo | Sources / citations |
| Dữ liệu giả để dev | Synthetic data |
| Tập câu hỏi chuẩn | Golden set |

---

## Phụ lục B — Flow một câu hỏi (ví dụ)

**User:** *"Net premium khác gross premium chỗ nào?"*

1. **Rewrite** — (không history) giữ nguyên.  
2. **Expand** — glossary thêm `phí thuần`, `phí gộp`, …  
3. **Hybrid search** — dense bắt nghĩa "phí"; sparse bắt exact terms.  
4. **RRF** — gộp ranking.  
5. **Rerank** — top chunks glossary / policy giải thích phí thuần & phí gộp.  
6. **Generate** — trả lời tiếng Việt, cite `[…, …]`, có thể kèm ký hiệu `$P$`, `$G$`.  
7. **UI** — KaTeX render; cuối có block **Nguồn tham khảo**.

---

## Phụ lục C — Lệnh "cheat sheet" copy-paste

```bash
# Start
cp .env.example .env && docker compose up -d --build
bash scripts/setup_models.sh          # lần đầu, cần mạng
bash scripts/healthcheck.sh

# Data
docker compose exec api python scripts/make_synthetic_data.py
bash scripts/ingest.sh data/glossary
bash scripts/ingest.sh data/synthetic

# Test
docker compose exec api pytest tests/ -x -q
docker compose exec api python eval/run_ragas.py --retrieval-only

# Chat UI
open http://localhost:3000            # macOS
# hoặc trình duyệt → http://localhost:3000

# Stop
docker compose down
```

---

*Tài liệu này mô tả trạng thái repo theo `README.md` / `CLAUDE.md` / skill
pipeline. OCR scan đầy đủ và tối ưu latency reranker trên CPU vẫn nằm trong
phần "Next" của project — đừng ngạc nhiên nếu `.png` ingest chưa được.*
