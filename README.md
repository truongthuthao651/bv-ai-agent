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
#    - Đặt ADMIN_PASSWORD trong .env nếu máy này có người khác dùng chung
#      (bảo vệ trang quản trị http://localhost:8000 bằng mật khẩu)

# 3) Cài đặt một lần (tạo môi trường Python + tải toàn bộ mô hình — cần mạng)
bash scripts/setup_native.sh

# 4) Khởi động hệ thống (lần đầu hãy chạy khi còn mạng — Open WebUI tải một
#    thành phần nhỏ ở lần khởi động đầu tiên; các lần sau hoàn toàn offline)
bash scripts/run_native.sh

# 5) Kiểm tra hệ thống
bash scripts/healthcheck.sh

# 6) Cài đặt tính năng "Nạp tài liệu" ngay trong Open WebUI (một lần, xem
#    scripts/open_webui/README.md để biết chi tiết từng bước)

# 7) Tạo tài khoản & phân quyền (một lần)
#    - Mở http://localhost:3000 và ĐĂNG KÝ tài khoản ĐẦU TIÊN — tài khoản này
#      tự động trở thành admin (đặt mật khẩu mạnh, đây là tài khoản quản trị).
#    - Cho phép nhân viên thấy trợ lý: Admin Panel → Settings → Models →
#      "bao-viet-life" → Visibility: Public → Save. (Mặc định Open WebUI ẩn
#      mọi model với người dùng thường; các model gốc qwen3/qwen2.5vl cứ để
#      riêng tư — nhân viên chỉ cần thấy "Trợ lý AI Bảo Việt Life".)
#    - Tạo tài khoản cho từng nhân viên: Admin Panel → Users → "+" (vai trò
#      "user"). Đăng ký công khai đã tắt — chỉ admin tạo được tài khoản.

# 8) Mở giao diện
#    Trình duyệt: http://localhost:3000  (Open WebUI — đăng nhập rồi trò chuyện)
#    Trang quản trị (chỉ mở được TRÊN máy chủ này): http://localhost:8000
#    API sức khỏe: http://localhost:8000/health
```

Dừng hệ thống: `bash scripts/stop_native.sh`. Nhật ký chạy nằm trong `logs/`.

> **Phân quyền (RBAC):** nhân viên đăng nhập và chỉ chat; mọi chức năng quản
> trị (nạp/xoá tài liệu, cấu hình, tạo tài khoản) chỉ admin thấy. Cụ thể:
> Open WebUI yêu cầu đăng nhập (`WEBUI_AUTH=true`), API cổng 8000 chỉ nghe
> trên `127.0.0.1` (`API_HOST` trong `.env`) nên nhân viên trong mạng LAN
> không truy cập được trang quản trị hay gọi thẳng API nạp/xoá tài liệu.
> KHÔNG đổi `WEBUI_AUTH` về `false` sau khi đã có tài khoản — Open WebUI sẽ
> từ chối khởi động. Nếu máy chủ này có người khác dùng chung (không chỉ
> admin), đặt thêm `ADMIN_PASSWORD` trong `.env` — trang quản trị sẽ yêu cầu
> đăng nhập riêng tại `http://localhost:8000/login` trước khi cho nạp/xoá tài
> liệu hay xem trang quản trị (để trống = không yêu cầu, như trước đây).

> **Nạp tài liệu (chỉ admin):** admin nạp tài liệu ngay trong Open WebUI
> (chọn model "📥 Nạp tài liệu", đính kèm tệp, gửi) — xem
> `scripts/open_webui/README.md` cho bước cài đặt một lần. Giữ model này ở
> chế độ Private (mặc định) để nhân viên không thấy nó. Trang
> `http://localhost:8000` là tiện ích quản trị trên máy chủ (trạng thái hệ
> thống, danh sách tài liệu, nạp/hỏi thử nhanh) — không bắt buộc dùng hằng ngày.

> **Thời gian trả lời:** dưới mỗi câu trả lời có dòng nhỏ "⏱ Thời gian trả lời:
> 1m55s" cho biết hệ thống mất bao lâu để trả lời (tính từ lúc nhận câu hỏi đến
> khi xong). Tắt bằng `SHOW_RESPONSE_TIME=false`. Hệ thống cũng ghi lại thời
> gian này (chỉ số liệu tổng hợp, **không** lưu nội dung câu hỏi/câu trả lời) vào
> `logs/query_timings.jsonl` để phân tích và cải thiện tốc độ về sau — hoàn toàn
> cục bộ, không gửi đi đâu. Tắt bằng `QUERY_TIMING_LOG_ENABLED=false`.

> **Liên kết trích dẫn cho người dùng trong mạng LAN:** phần "Nguồn tham khảo"
> tạo liên kết từ `API_PUBLIC_BASE_URL`. Mặc định là `http://localhost:8000`, nên
> liên kết chỉ bấm được khi mở TRÊN máy chủ; nhân viên ở máy khác trong mạng LAN
> bấm vào sẽ mở `localhost` của chính họ (không có gì). Muốn nhân viên bấm được:
> đặt `API_PUBLIC_BASE_URL` thành địa chỉ LAN của máy chủ (ví dụ
> `http://192.168.1.20:8000`), đặt `API_HOST=0.0.0.0` để hai tuyến chỉ-đọc
> `/documents/{id}/view` và `/file` mở được từ LAN, và GIỮ `ADMIN_PASSWORD` để
> chức năng nạp/xoá vẫn được bảo vệ. Khi giá trị này là loopback, API ghi một
> cảnh báo lúc khởi động. Để nguyên nếu chấp nhận trích dẫn chỉ dùng trên máy chủ.

> **Giao diện thương hiệu Bảo Việt:** logo, màu xanh/vàng thương hiệu và các
> câu hỏi gợi ý (thuật ngữ định phí, quy trình nội bộ…) được tự động áp dụng
> bởi `scripts/open_webui/apply_branding.py` — chạy sẵn trong `setup_native.sh`
> và mỗi lần `run_native.sh` khởi động Open WebUI. Lưu ý: gợi ý câu hỏi tiếng
> Việt xuất hiện từ **lần khởi động thứ hai** trở đi (lần đầu Open WebUI mới
> tạo cơ sở dữ liệu cấu hình). Nếu nâng cấp `open-webui` bằng pip, chỉ cần
> khởi động lại bằng `run_native.sh` là thương hiệu được áp dụng lại.

> **Trợ lý tư vấn / so sánh sản phẩm:** với câu hỏi mang tính so sánh hoặc
> khuyến nghị ("so sánh quyền lợi A và B", "khách hàng nên chọn sản phẩm nào?"),
> trợ lý được phép **đối chiếu và tổng hợp trên các dữ kiện đã trích dẫn** thay
> vì từ chối. Mọi số liệu vẫn phải lấy từ tài liệu, vẫn từ chối nếu hỏi về sản
> phẩm không có trong kho, và phần gợi ý luôn kèm ghi chú "không phải tư vấn
> sản phẩm chính thức". Tắt bằng `ADVISORY_MODE_ENABLED=false` trong `.env`.
> Trợ lý cũng có thể thêm một mục **"Kiến thức chung (ngoài tài liệu)"** ở cuối
> câu trả lời (kiến thức bảo hiểm tổng quát, có gắn nhãn rõ, không chứa số liệu
> nội bộ) — tắt bằng `GENERAL_KNOWLEDGE_SUPPLEMENT_ENABLED=false`.

> **Kho tài liệu tham khảo công khai (knowledge pack):** hệ thống **không** tra
> cứu Internet — nó chạy hoàn toàn ngoại tuyến. Muốn trợ lý biết thêm luật,
> thông tư hay brochure đã công bố, hãy **tải thủ công** các tệp công khai đó về
> `data/knowledge_pack/`, sao chép `manifest.example.yaml` thành `manifest.yaml`,
> ghi tiêu đề + địa chỉ gốc của từng tệp, rồi chạy:
>
> ```bash
> bash scripts/stop_native.sh                          # Qdrant nhúng chỉ 1 tiến trình
> python scripts/ingest_knowledge_pack.py --dry-run    # kiểm tra manifest trước
> python scripts/ingest_knowledge_pack.py              # nạp vào kho
> bash scripts/run_native.sh
> ```
>
> Khi trợ lý dùng các tài liệu này, phần "Nguồn tham khảo" sẽ hiển thị **liên
> kết tới địa chỉ công khai gốc** kèm nhãn "(nguồn công khai)", để nhân viên bấm
> vào kiểm chứng. Ứng dụng không bao giờ tự truy cập địa chỉ đó. **Chỉ đặt tài
> liệu CÔNG KHAI vào đây** — tài liệu nội bộ nạp qua Open WebUI như bình thường.
> Cách khác cho một tệp lẻ: nạp qua trang quản trị và điền ô "Nguồn URL công khai".

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

**Bảo Việt branding:** `scripts/open_webui/apply_branding.py` patches the
pip-installed Open WebUI in place (offline): BV logo/favicon/splash, brand
blue/gold accents, Vietnamese default locale, and actuarial/internal-document
prompt suggestions (from `scripts/open_webui/prompt_suggestions.json`). It
runs automatically in `setup_native.sh` and before each Open WebUI start in
`run_native.sh`; the suggestion swap takes effect from the second start
(Open WebUI creates its config DB on first boot). Suggestions customized
later in the Admin UI are never overwritten (use `--force` to reset them).
The Docker dev stack uses the stock Open WebUI image and is not branded.

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
python scripts/ingest_knowledge_pack.py --dry-run   # validate the public-reference manifest
python scripts/ingest_knowledge_pack.py     # index public refs — native: stop the API first
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
retrieval (glossary query expansion, a pre-retrieval typo-confirmation gate —
`app/retrieval/spellcheck.py`, `SPELLCHECK_ENABLED` — that asks the user to
confirm before answering when the query likely garbles a known glossary term
or document title, LLM standalone-question rewrite with sticky conversation
scope — `CONVERSATION_SCOPE_ENABLED` — that reinjects the last-cited document
title into follow-ups that drop the product name, hybrid RRF-fused search,
bge-reranker-v2-m3 reranking with a relevance floor — `RERANK_MIN_SCORE` —
that falls back to a clearly-labeled general-knowledge answer or refuses
deterministically, per `HYBRID_FALLBACK_ENABLED` (scoped company-document
follow-ups always refuse rather than hybrid-fallback), when nothing relevant is
found) and generation (Vietnamese system prompt with
citations/refusal/math-disclaimer/Mermaid-chart rules, SSE streaming, an
appended "Nguồn tham khảo" sources block whose document titles are hyperlinks
back to `GET /documents/{doc_id}/file`, a deterministic calculation guardrail
that appends the "Kết quả cần được kiểm tra lại..." disclaimer whenever an
answer contains computed numbers even if the model forgot it, and Ollama
`keep_alive` so the model stays warm between questions) via
`POST /v1/chat/completions`;
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
role-based access (`WEBUI_AUTH=true`): the first registered account is the
admin, who creates employee accounts (public signup off) and publishes only
the `bao-viet-life` model to them — employees log in and chat, while the
Admin Panel, raw Ollama models, the ingest pipe, and the port-8000 admin
page/API (bound to `127.0.0.1` via `API_HOST`, and additionally gated by a
single shared password — `ADMIN_PASSWORD`, `app/auth.py`, login page at
`/login` — when set) stay admin/machine-only;
Docker-free native deployment (`scripts/setup_native.sh` / `run_native.sh` /
`stop_native.sh`, embedded in-process Qdrant via `QDRANT_LOCAL_PATH`, pandoc
bundled via `pypandoc-binary`) for company machines where Docker isn't allowed.

**Next:** scanned-document OCR (PaddleOCR + formula-OCR + figures), and
reranker latency reduction on CPU-only machines (measured ~50s/query on an
M1 CPU container — see the api logs' `retrieval timings`).

See `CLAUDE.md` for architecture and the non-negotiable security rules, and
`.claude/skills/insurance-rag-pipeline/SKILL.md` for the implementation guide.
