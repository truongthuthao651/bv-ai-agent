# Trợ lý AI Bảo Việt Life — RAG nội bộ cho tài liệu công ty

> **Local RAG Assistant for a Vietnamese Life Insurance Firm** — English section below.

Trợ lý AI chạy **hoàn toàn nội bộ** (offline) giúp nhân viên tra cứu và hỏi đáp
về tài liệu công ty: hợp đồng, quy trình, biểu mẫu, bảng tính, hình ảnh scan.

> **Thương hiệu:** tên hiển thị ("Trợ lý AI Bảo Việt Life") đặt qua `ASSISTANT_NAME`
> / `WEBUI_NAME` trong `.env` — chỉ là phần hiển thị, mô hình chạy nền không đổi.
> Đổi các giá trị này (và `ASSISTANT_MODEL_ID` / `DEFAULT_MODELS`) để đổi thương hiệu.
Câu trả lời bằng **tiếng Việt**, có **trích dẫn nguồn**, và **hiển thị công thức
toán** (LaTeX). Toàn bộ dữ liệu **không rời khỏi máy** — không gọi API bên ngoài.

- **Mô hình (qua Ollama):** chat `qwen3:8b`, thị giác `qwen2.5vl:7b`, embedding `bge-m3`
- **Cơ sở dữ liệu vector:** Qdrant (tìm kiếm hybrid dense + sparse), rerank `bge-reranker-v2-m3`
- **Giao diện:** Open WebUI trỏ tới API FastAPI (hiển thị LaTeX bằng KaTeX)

> ⚠️ **Bảo mật:** Thư mục `data/real/` chứa tài liệu mật của công ty — **không bao
> giờ** đưa vào Git, không đọc trong quá trình phát triển. Chỉ dùng `data/synthetic/`
> khi phát triển/kiểm thử.

---

## 🚀 Hướng dẫn triển khai (dành cho người quản lý cài đặt trên máy công ty)

Yêu cầu: máy đã cài **Docker Desktop** (hoặc Docker Engine + Compose). Có GPU
NVIDIA thì tốt hơn nhưng không bắt buộc.

```bash
# 1) Lấy mã nguồn
git clone <repo-url> insurance-assistant
cd insurance-assistant

# 2) Tạo file cấu hình cho máy này (chỉnh nếu cần)
cp .env.example .env
#    - Máy yếu: sửa CHAT_MODEL=qwen3:4b trong .env
#    - Đổi cổng nếu bị trùng: API_PORT, OPEN_WEBUI_PORT

# 3) Khởi động toàn bộ hệ thống (CPU)
docker compose up -d
#    Nếu có GPU NVIDIA:
#    docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# 4) Tải các mô hình (chỉ cần mạng ở bước này)
bash scripts/setup_models.sh

# 5) Kiểm tra hệ thống
bash scripts/healthcheck.sh

# 6) Cài đặt tính năng "Nạp tài liệu" ngay trong Open WebUI (một lần, xem
#    scripts/open_webui/README.md để biết chi tiết từng bước)

# 7) Mở giao diện
#    Trình duyệt: http://localhost:3000  (Open WebUI — trò chuyện + nạp tài liệu)
#    Trang quản trị (tuỳ chọn, để xem trạng thái hệ thống): http://localhost:8000
#    API sức khỏe: http://localhost:8000/health
```

Dừng hệ thống: `docker compose down` (thêm `-v` để xoá cả dữ liệu volume).

> **Nạp tài liệu:** người dùng nạp tài liệu ngay trong Open WebUI (chọn model
> "📥 Nạp tài liệu", đính kèm tệp, gửi) — xem `scripts/open_webui/README.md`
> cho bước cài đặt một lần (admin). Trang `http://localhost:8000` là một tiện
> ích quản trị tuỳ chọn (trạng thái hệ thống, danh sách tài liệu, nạp/hỏi thử
> nhanh) — không bắt buộc dùng hằng ngày.

> Mọi giá trị đặc thù theo máy nằm trong `.env`, **không** nằm trong mã nguồn.

---

## English

A **fully-local, offline** ChatGPT-like assistant that answers employees'
questions about company documents (policies, procedures, forms, spreadsheets,
scanned images). Answers are in **Vietnamese**, **grounded with citations**, and
render **math formulas** as LaTeX. Nothing leaves the machine — no external API calls.

- **Serving (Ollama):** chat `qwen3:8b`, vision `qwen2.5vl:7b`, embeddings `bge-m3`
- **Vector DB:** Qdrant (hybrid dense + sparse), reranker `bge-reranker-v2-m3`
- **Frontend:** Open WebUI pointed at the FastAPI endpoint (KaTeX for LaTeX)

See the deployment steps above (they are the same commands). Development uses
`data/synthetic/` only; `data/real/` is confidential and never touched.

### Local dev on Apple Silicon (Metal GPU)

Docker Desktop on macOS **cannot pass through any GPU** (NVIDIA or Apple Metal),
so the in-compose `ollama` service is always CPU-only on a Mac. For real GPU
acceleration on an Apple Silicon dev machine, run Ollama **natively** (it uses
Metal automatically) and point the API container at it:

```bash
# 1) Stop the in-compose Ollama so it doesn't hold port 11434
docker compose stop ollama
# 2) Run native, Metal-accelerated Ollama bound so the container can reach it
OLLAMA_HOST=0.0.0.0:11434 ollama serve &
ollama pull qwen3:1.7b          # chat model (embeddings use local ./models/bge-m3, not Ollama)
# 3) Point the API at the host, then recreate just the API container
#    (.env)  OLLAMA_BASE_URL=http://host.docker.internal:11434
docker compose up -d --no-deps api
```

Measured on this repo (M1 Pro): a formula answer dropped from ~440s (Docker CPU,
reasoning on) to ~56s (native Metal, `LLM_THINKING=false`). The NVIDIA deployment
box is unaffected — it keeps `OLLAMA_BASE_URL=http://ollama:11434` and the GPU override.

### Common commands

```bash
docker compose up -d                                                   # start (CPU)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d   # start (GPU)
bash scripts/setup_models.sh                                           # pull models
bash scripts/healthcheck.sh                                            # smoke test
pytest tests/ -x -q                                                    # unit tests (no Docker)
docker compose exec api python eval/run_ragas.py                       # golden-set eval (needs stack up)
ruff check app/ && ruff format app/                                    # lint + format
```

### Project status

**Done:** foundation (directory structure, `settings.py`, Docker Compose CPU+GPU,
Dockerfile, `requirements.txt`, `/health`, setup/healthcheck scripts, starter
glossary); Markdown/DOCX/XLSX/PDF/glossary ingestion (parsing, equation-safe
chunking, spreadsheet-to-Markdown-table conversion, Docling PDF parsing with
formula enrichment + header/footer cleaning, formula verbalization, bge-m3
dense+sparse indexing into Qdrant) via `POST /ingest` and batch via
`scripts/ingest.sh`;
retrieval (glossary query expansion, LLM standalone-question rewrite, hybrid
RRF-fused search, bge-reranker-v2-m3 reranking with a relevance floor —
`RERANK_MIN_SCORE` — that refuses deterministically when nothing relevant is
found) and generation (Vietnamese system prompt with
citations/refusal/math-disclaimer rules, SSE streaming, an appended
"Nguồn tham khảo" sources block, a deterministic calculation guardrail that
appends the "Kết quả cần được kiểm tra lại..." disclaimer whenever an answer
contains computed numbers even if the model forgot it, and Ollama `keep_alive`
so the model stays warm between questions) via `POST /v1/chat/completions`;
document deletion via
`DELETE /documents/{doc_id}` (with a delete button on the admin page);
per-stage latency logging (rewrite/search/rerank/first-token) in the api logs;
a 32-question golden set (27 Vietnamese + 5 English — glossary synonym
expansion bridges English queries to Vietnamese documents) plus an offline
eval harness —
`docker compose exec api python eval/run_ragas.py` — reporting retrieval hit
rates/MRR, refusal & citation compliance, and LLM-judged
correctness/faithfulness, with per-run JSON under `eval/results/`;
document upload wired into the user-facing Open WebUI chat itself via a Pipe
function (`scripts/open_webui/ingest_pipe.py`), plus an optional admin page
(`http://localhost:8000`) for system status / manual upload / quick testing.

**Next:** scanned-document OCR (PaddleOCR + formula-OCR + figures), and
reranker latency reduction on CPU-only machines (measured ~50s/query on an
M1 CPU container — see the api logs' `retrieval timings`).

See `CLAUDE.md` for architecture and the non-negotiable security rules, and
`.claude/skills/insurance-rag-pipeline/SKILL.md` for the implementation guide.
