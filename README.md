# Trợ lý AI nội bộ (RAG) cho tài liệu công ty bảo hiểm nhân thọ

> **Local RAG Assistant for a Vietnamese Life Insurance Firm** — English section below.

Trợ lý AI chạy **hoàn toàn nội bộ** (offline) giúp nhân viên tra cứu và hỏi đáp
về tài liệu công ty: hợp đồng, quy trình, biểu mẫu, bảng tính, hình ảnh scan.
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

# 6) Nạp dữ liệu (khi các bước ingestion đã sẵn sàng — Phase sau)
#    bash scripts/ingest.sh data/glossary
#    bash scripts/ingest.sh data/synthetic     # dev/test
#    (Trên máy công ty: nạp tài liệu thật từ thư mục nội bộ — KHÔNG commit)

# 7) Mở giao diện
#    Trình duyệt: http://localhost:3000  (Open WebUI)
#    API sức khỏe: http://localhost:8000/health
```

Dừng hệ thống: `docker compose down` (thêm `-v` để xoá cả dữ liệu volume).

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

### Common commands

```bash
docker compose up -d                                                   # start (CPU)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d   # start (GPU)
bash scripts/setup_models.sh                                           # pull models
bash scripts/healthcheck.sh                                            # smoke test
pytest tests/ -x -q                                                    # unit tests (no Docker)
ruff check app/ && ruff format app/                                    # lint + format
```

### Project status

**Done:** foundation (directory structure, `settings.py`, Docker Compose CPU+GPU,
Dockerfile, `requirements.txt`, `/health`, setup/healthcheck scripts, starter
glossary); Markdown/DOCX ingestion (parsing, equation-safe chunking, formula
verbalization, bge-m3 dense+sparse indexing into Qdrant) via `POST /ingest`;
retrieval (glossary query expansion, LLM standalone-question rewrite, hybrid
RRF-fused search, bge-reranker-v2-m3 reranking) and generation (Vietnamese
system prompt with citations/refusal/math-disclaimer rules, SSE streaming) via
`POST /v1/chat/completions`; a 21-question golden set (`eval/golden_set.jsonl`).

**Next:** hard parsers (PDF/XLSX/image/OCR/formula-OCR/figures — Increment D),
and wiring `eval/run_ragas.py` against the golden set.

See `CLAUDE.md` for architecture and the non-negotiable security rules, and
`.claude/skills/insurance-rag-pipeline/SKILL.md` for the implementation guide.
