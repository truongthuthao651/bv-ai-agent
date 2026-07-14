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

**Không cần Docker.** Toàn bộ hệ thống chạy trực tiếp trên máy (macOS / Linux).
Yêu cầu duy nhất, cài một lần:

1. **Python 3.11 hoặc 3.12** — https://www.python.org/downloads/
2. **Ollama** (phần mềm chạy mô hình AI cục bộ) — https://ollama.com

Chỉ cần mạng Internet ở bước cài đặt (tải thư viện + mô hình); sau đó hệ
thống chạy **hoàn toàn offline**. Cơ sở dữ liệu vector (Qdrant) chạy **nhúng
ngay trong ứng dụng** — không phải cài thêm gì.

```bash
# 1) Lấy mã nguồn
git clone <repo-url> bv-ai-agent
cd bv-ai-agent

# 2) Tạo file cấu hình cho máy này (chỉnh nếu cần)
cp .env.example .env
#    - Máy yếu: sửa CHAT_MODEL=qwen3:4b trong .env
#    - Đổi cổng nếu bị trùng: API_PORT, OPEN_WEBUI_PORT

# 3) Cài đặt một lần (tạo môi trường Python + tải toàn bộ mô hình — cần mạng)
bash scripts/setup_native.sh

# 4) Khởi động hệ thống (lần đầu hãy chạy khi còn mạng — Open WebUI tải một
#    thành phần nhỏ ở lần khởi động đầu tiên; các lần sau hoàn toàn offline)
bash scripts/run_native.sh

# 5) Kiểm tra hệ thống
bash scripts/healthcheck.sh

# 6) Cài đặt tính năng "Nạp tài liệu" ngay trong Open WebUI (một lần, xem
#    scripts/open_webui/README.md để biết chi tiết từng bước)

# 7) Mở giao diện
#    Trình duyệt: http://localhost:3000  (Open WebUI — trò chuyện + nạp tài liệu)
#    Trang quản trị (tuỳ chọn, để xem trạng thái hệ thống): http://localhost:8000
#    API sức khỏe: http://localhost:8000/health
```

Dừng hệ thống: `bash scripts/stop_native.sh`. Nhật ký chạy nằm trong `logs/`.

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

**Deployment is Docker-free** (company machines don't allow Docker): the
`scripts/*_native.sh` scripts run everything directly — the API in a local
venv (pandoc bundled via `pypandoc-binary`), Open WebUI pip-installed in its
own venv, and Qdrant **embedded in-process** via qdrant-client local mode
(`QDRANT_LOCAL_PATH` in `.env`; empty switches back to server mode at
`QDRANT_URL`). Only Python 3.11/3.12 and Ollama need to be installed. See the
deployment steps above (same commands). Development uses `data/synthetic/`
only; `data/real/` is confidential and never touched.

> Embedded-mode caveat: the storage directory is single-process. Stop the API
> (`bash scripts/stop_native.sh`) before running `eval/run_ragas.py` natively.

### Optional: Docker dev stack

`docker-compose.yml` still works for dev machines that have Docker
(`docker compose up -d`; add `docker-compose.gpu.yml` for an NVIDIA GPU).
The container always uses server-mode Qdrant — compose overrides
`QDRANT_LOCAL_PATH` internally — but `OLLAMA_BASE_URL` is substituted from
`.env`: delete that line from `.env` to use the in-compose `ollama` service,
or point it at `http://host.docker.internal:11434` for a native Ollama (next
section).

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
bash scripts/setup_native.sh                # one-time native setup (venvs + all models)
bash scripts/run_native.sh                  # start the stack natively (no Docker)
bash scripts/stop_native.sh                 # stop it
bash scripts/setup_models.sh                # (re-)pull models — autodetects native vs docker
bash scripts/healthcheck.sh                 # smoke test
pytest tests/ -x -q                         # unit tests (no services needed)
.venv/bin/python eval/run_ragas.py          # golden-set eval — native: stop the API first
ruff check app/ && ruff format app/         # lint + format
docker compose up -d                        # optional Docker dev stack (CPU)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d   # …with NVIDIA GPU
docker compose exec api python eval/run_ragas.py                       # eval inside Docker
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
(`http://localhost:8000`) for system status / manual upload / quick testing;
Docker-free native deployment (`scripts/setup_native.sh` / `run_native.sh` /
`stop_native.sh`, embedded in-process Qdrant via `QDRANT_LOCAL_PATH`, pandoc
bundled via `pypandoc-binary`) for company machines where Docker isn't allowed.

**Next:** scanned-document OCR (PaddleOCR + formula-OCR + figures), and
reranker latency reduction on CPU-only machines (measured ~50s/query on an
M1 CPU container — see the api logs' `retrieval timings`).

See `CLAUDE.md` for architecture and the non-negotiable security rules, and
`.claude/skills/insurance-rag-pipeline/SKILL.md` for the implementation guide.
