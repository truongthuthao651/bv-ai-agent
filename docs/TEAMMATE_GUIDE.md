# Hướng dẫn cho thành viên dự án

## Mục tiêu

Dự án là trợ lý RAG nội bộ cho tài liệu bảo hiểm. Ứng dụng chạy cục bộ với
Ollama, FastAPI, Open WebUI và Qdrant nhúng trong tiến trình API. Không gửi dữ
liệu công ty tới API bên ngoài.

## Quy tắc bảo mật bắt buộc

1. Không đọc, liệt kê hoặc tham chiếu bất cứ nội dung nào dưới `data/real/`.
2. Chỉ dùng `data/synthetic/` cho phát triển, kiểm thử và ví dụ.
3. Không đưa dữ liệu thật, tệp `.env`, model, Qdrant storage hoặc log vào Git.
4. Không thêm telemetry, analytics hoặc external API vào mã ứng dụng.
5. Mọi cấu hình phải đi qua `app/config/settings.py`; không gọi `os.getenv()`
   trực tiếp ở nơi khác.

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
             │  :11434    │                  │ embedded   │                  │ (HF weights│
             │ chat+vision│                  │ in FastAPI │                  │ embed/rerank│
             └────────────┘                  └────────────┘                  └────────────┘
```

Admin UI tuỳ chọn: `http://localhost:8000` (upload / health / hỏi thử nhanh).
User hàng ngày chủ yếu dùng Open WebUI `:3000`.

Qdrant chạy **nhúng ngay trong process FastAPI** và lưu vào
`qdrant_storage/local/` (`QDRANT_LOCAL_PATH`). Ba process Ollama, FastAPI và
Open WebUI do `scripts/run_native.sh` quản lý.

### Stack chi tiết (tools & technologies)

| Lớp | Công nghệ | Vai trò | Ghi chú |
|-----|-----------|---------|---------|
| **Orchestration** | Scripts native (`scripts/run_native.sh`) | Ollama + API (Qdrant nhúng) + Open WebUI | Chạy bằng Git Bash trên Windows hoặc Bash trên macOS/Linux |
| **API** | FastAPI + Uvicorn | HTTP API, SSE streaming, lifespan warmup | `app/main.py` |
| **Config** | pydantic-settings | Mọi biến đọc từ `.env` qua `settings.py` | Không `os.getenv()` lung tung |
| **Chat LLM** | Ollama + Qwen3 (`qwen3:8b`) | Sinh câu trả lời tiếng Việt | Máy yếu: `qwen3:4b` |
| **Vision LLM** | Ollama + Qwen2.5-VL (`qwen2.5vl:7b`) | Mô tả biểu đồ / OCR công thức (enrichment) | Chậm — chỉ lúc ingest |
| **Embeddings** | FlagEmbedding `bge-m3` | Dense + sparse vectors | **Không** qua Ollama (Ollama không đủ sparse) |
| **Reranker** | `bge-reranker-v2-m3` | Cross-encoder xếp lại top hits | Có sàn điểm `RERANK_MIN_SCORE` |
| **Vector DB** | Qdrant client local mode | Named vectors `dense` / `sparse` | Chạy **nhúng trong API** (`QDRANT_LOCAL_PATH`), single-process; telemetry tắt |
| **PDF parse** | Docling (`do_formula_enrichment`) | PDF → Markdown + LaTeX | Weights trong `./models/docling` |
| **DOCX parse** | pandoc (`gfm+tex_math_dollars`) | Word OMML → LaTeX | **Không** dùng `python-docx` làm path chính (nó drop equation) |
| **XLSX** | pandas / openpyxl | Sheet → Markdown table | Header lặp lại mỗi chunk |
| **OCR (WIP)** | PaddleOCR `lang=vi` + formula OCR | Scan / ảnh | Chưa bật end-to-end — image parser raise `NotImplementedError` |
| **Frontend** | Open WebUI 0.5.4 | Chat UI, KaTeX cho LaTeX | Trỏ `OPENAI_API_BASE_URL` vào FastAPI |
| **Upload từ UI** | Open WebUI Pipe (`ingest_pipe.py`) | Model giả "📥 Nạp tài liệu" → `POST /ingest` | Setup 1 lần (admin) |
| **Eval** | `eval/run_ragas.py` + golden set | Hit rate, faithfulness, refusal, citation | Offline, không phụ thuộc package `ragas` |
| **Lint / test** | ruff, pytest | Unit test không cần service đang chạy | `tests/` dùng fixture synthetic |

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
│   ├── setup_native.sh       # Setup native (venvs + models) — một lần
│   ├── run_native.sh         # Start stack native (ollama + api + webui)
│   ├── stop_native.sh        # Stop stack native
│   ├── setup_models.sh       # ollama pull + HF download
│   ├── healthcheck.sh        # Smoke test Ollama, API/Qdrant và Open WebUI
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
    │                  (bỏ sticky 1-sản-phẩm nếu câu hỏi đã nêu ≥2 sản phẩm)
    ▼
query_expansion.py   # "net premium" → thêm "phí thuần" (từ glossary, không gọi LLM)
    │
    ▼
hybrid_search        # dense top-20 + sparse top-20 → RRF fusion
    │                  (câu so sánh ≥2 SP: search+rerank *từng* SP rồi merge —
    │                   comparison.py; tránh 1 SP chiếm hết top-k)
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

### 7.1 Quy tắc trả lời (không được làm yếu trong `prompts.py`)

1. **Chỉ trả lời từ ngữ cảnh** đã retrieve — không bịa.
2. **Trích dẫn** dạng `[Tên tài liệu, mục X]`.
3. Không đủ thông tin → đúng câu:
   `Tôi không tìm thấy thông tin trong tài liệu.`
4. Có tính toán số → hiện công thức LaTeX + bước thay số + disclaimer:
   `Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức.`
   (Model local 7–8B **không** đáng tin cho số liệu bảo hiểm.)
5. **Loại trừ:** nếu ngữ cảnh ghi hoạt động thuộc loại trừ / không chi trả →
   kết luận **không** được bảo hiểm. Không được đảo chiều polar
   (lỗi hay gặp của model nhỏ: đọc "loại trừ" rồi kết luận "được bao gồm").
6. **Loại chỉ số:** lãi suất cam kết / phí ≠ tỷ lệ bồi thường. Không đổi nhãn
   bảng; thiếu số liệu quyền lợi → refuse.

Ngoài prompt, code còn có **guardrail xác định**:

- Không còn hit sau `RERANK_MIN_SCORE` → refusal ngay (không gọi LLM).
- Answer có số liệu tính toán mà quên disclaimer → generator tự append.
- Câu hỏi claim/% quyền lợi → `METRIC_GUARD_ENABLED` loại hit phí / lãi suất
  cam kết trước khi generate (tránh trả lời claim bằng bảng lãi suất).

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

Hệ thống chỉ hỗ trợ chạy native. Trên Windows dùng Git Bash; trên macOS/Linux
dùng Bash. Cài **uv** (ưu tiên) và **Ollama**. Nếu không có uv, cần Python
3.11 hoặc 3.12 đã cài sẵn. Qdrant chạy **nhúng ngay trong API**, không cần cài
server riêng.

- ~20–40 GB trống cho models (tuỳ CHAT_MODEL)
- Git clone repo này

### 9.1 Lần đầu — setup đầy đủ

```bash
cp .env.example .env
bash scripts/setup_native.sh
bash scripts/run_native.sh
bash scripts/healthcheck.sh
```

`setup_native.sh` ưu tiên uv và Python 3.12. Khi uv không có, script tự dùng
Python 3.11/3.12 với `venv` và `pip`. Môi trường ứng dụng là `.venv`; Open
WebUI dùng `.venv-webui`. Không cài phụ thuộc dự án vào Python hệ thống.

Lệnh hữu ích:

```bash
bash scripts/stop_native.sh
bash scripts/setup_models.sh
bash scripts/ingest.sh data/synthetic
.venv/Scripts/python.exe -m pytest tests/ -x -q  # Windows Git Bash
.venv/bin/python -m pytest tests/ -x -q          # macOS/Linux
```

Qdrant chạy nhúng khi `QDRANT_LOCAL_PATH` có giá trị. Dừng API trước khi chạy
`eval/run_ragas.py`, vì thư mục storage chỉ cho phép một tiến trình truy cập.

## Kiến trúc

- `app/api/`: API chat, ingest, health và quản trị.
- `app/ingestion/`: parser, chuẩn hóa, chunking, enrichment và indexing.
- `app/retrieval/`: mở rộng truy vấn, truy xuất hybrid, guardrail và rerank.
- `app/generation/`: prompt tiếng Việt, gọi Ollama và câu trả lời có trích dẫn.
- `scripts/`: setup, start, stop, healthcheck, ingest và công cụ Open WebUI.

Biểu diễn chuẩn của tài liệu là Markdown với LaTeX. Không tách công thức khỏi
đoạn giải thích. Câu trả lời phải dựa trên tài liệu truy xuất được, có trích dẫn
nguồn, và phải từ chối khi ngữ cảnh không đủ.

## Kiểm thử và chất lượng

Chạy test bằng Python của môi trường ứng dụng. Dùng `ruff check app/` để kiểm
tra tĩnh; chỉ chạy formatter khi thay đổi định dạng được yêu cầu. Kết quả đánh
giá được ghi vào `eval/results/` và không được commit.

Khi thay đổi dependency, giữ phiên bản được pin chính xác. Khi thay đổi luồng
setup hoặc vận hành, cập nhật README và hướng dẫn này cùng lúc.
