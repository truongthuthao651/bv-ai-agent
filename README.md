# Trợ lý AI Bảo Việt Life — RAG nội bộ cho tài liệu công ty

> **Local RAG Assistant for a Vietnamese Life Insurance Firm** — English section below.

Trợ lý AI chạy **hoàn toàn nội bộ** (offline) giúp nhân viên tra cứu và hỏi đáp
về tài liệu công ty: hợp đồng, quy trình, biểu mẫu, bảng tính, hình ảnh scan.

> **Thương hiệu:** tên hiển thị ("Trợ lý AI Bảo Việt Life") đặt qua `ASSISTANT_NAME`
> trong `.env` — chỉ là phần hiển thị, mô hình chạy nền không đổi. Đổi giá trị
> này (và `ASSISTANT_MODEL_ID`) để đổi thương hiệu.
Câu trả lời bằng **tiếng Việt**, có **trích dẫn nguồn**, và **hiển thị công thức
toán** (LaTeX). Toàn bộ dữ liệu **không rời khỏi máy** — không gọi API bên ngoài.

- **Mô hình (qua Ollama):** chat `qwen3:8b`, thị giác `qwen2.5vl:7b`, embedding `bge-m3`
- **Cơ sở dữ liệu vector:** Qdrant (tìm kiếm hybrid dense + sparse), rerank `bge-reranker-v2-m3`
- **Giao diện:** một ứng dụng React duy nhất, một cổng duy nhất (8000) — trang
  giới thiệu (`/`), giao diện trò chuyện (`/chat`, công thức LaTeX qua KaTeX
  tự lưu trữ — dùng được cho MỌI tài khoản), và trang quản trị (`/admin`, nạp/
  sửa/xoá tài liệu, số liệu — **chỉ tài khoản vai trò admin**). Đăng nhập bằng
  tài khoản email `@baoviet.com` (`app/accounts.py`, xem bước 7 dưới đây).
  Open WebUI đã được gỡ bỏ hoàn toàn.

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
#    - Đổi cổng nếu bị trùng: API_PORT
#    - Đặt SESSION_SECRET_KEY thành một chuỗi ngẫu nhiên cố định (xem chú thích
#      trong .env.example) để phiên đăng nhập /admin và /chat không bị đăng
#      xuất mỗi khi khởi động lại dịch vụ

# 3) Cài đặt một lần (Python + mô hình + build sẵn frontend — cần mạng;
#    cần Node/npm chỉ cho bước build frontend, KHÔNG cần trên máy triển khai
#    thật nếu bạn build sẵn ở máy dev rồi commit app/static/dist/)
bash scripts/setup_native.sh

# 4) Khởi động hệ thống (lần đầu hãy chạy khi còn mạng; sau đó hoàn toàn offline)
bash scripts/run_native.sh

# 5) Kiểm tra hệ thống
bash scripts/healthcheck.sh

# 6) Tạo tài khoản (một lần cho mỗi người — KHÔNG có đăng ký công khai,
#    admin tạo tài khoản bằng lệnh dưới đây; email phải @baoviet.com)
.venv/bin/python scripts/seed_accounts.py ban-quan-tri@baoviet.com "MatKhauManh1!" admin
.venv/bin/python scripts/seed_accounts.py nhanvien@baoviet.com "MatKhauManh2!" employee
#    - Tài khoản "admin" thấy đầy đủ /admin (nạp/sửa/xoá tài liệu, danh sách
#      tài khoản) VÀ dùng được /chat.
#    - Tài khoản "employee" CHỈ dùng được /chat — vào /admin sẽ tự động
#      chuyển hướng về /chat, và các API quản trị trả lỗi 403.
#    - Chưa dùng SSO nội bộ (không có sẵn) — xem CLAUDE.md, phần ghi chú ngay
#      dưới 5 quy tắc an toàn, nếu công ty sau này có SSO để chuyển sang.

# 7) Mở giao diện
#    Trang giới thiệu: http://localhost:8000
#    Trò chuyện:        http://localhost:8000/chat   (mọi tài khoản)
#    Trang quản trị:    http://localhost:8000/admin   (chỉ tài khoản admin —
#                        cũng có một nút "Mở trang quản trị" ngay trong /chat)
#    API sức khỏe:      http://localhost:8000/health
```

Dừng hệ thống: `bash scripts/stop_native.sh`. Nhật ký chạy nằm trong `logs/`.

> **Phân quyền (RBAC):** một hệ thống tài khoản duy nhất (`app/accounts.py`) —
> email `@baoviet.com` + mật khẩu, cấp bằng `scripts/seed_accounts.py`, không
> có đăng ký công khai. Vai trò "admin" dùng được cả `/admin` và `/chat`; vai
> trò "employee" chỉ dùng được `/chat`. Việc chặn `/admin` khỏi "employee" thực
> thi ở CẢ HAI lớp — không chỉ ẩn nút trên giao diện: vào thẳng `/admin` sẽ bị
> chuyển hướng về `/chat`, và mọi API quản trị (`GET/PATCH/DELETE /documents`,
> `GET /metrics/summary`, `GET /accounts`) trả 403 nếu gọi trực tiếp bằng tài
> khoản "employee". `API_HOST` mặc định `127.0.0.1` (chỉ máy chủ này) nên mọi
> tài khoản, kể cả "employee", chỉ đăng nhập được TỪ máy chủ trừ khi mở
> `API_HOST=0.0.0.0` (xem mục LAN bên dưới).

> **Nạp tài liệu (chỉ admin):** trang `/admin` (tài khoản vai trò admin) có
> màn hình "Tài liệu" với kéo-thả, sửa, xoá — chạm trực tiếp vào kho Qdrant.
> `/admin` cũng có trạng thái hệ thống, số liệu chất lượng, và hỏi thử nhanh —
> không bắt buộc dùng hằng ngày.

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
> `http://192.168.1.20:8000`), và đặt `API_HOST=0.0.0.0` để hai tuyến chỉ-đọc
> `/documents/{id}/view` và `/file` mở được từ LAN — tài khoản @baoviet.com
> (bước 7) vẫn bảo vệ nạp/sửa/xoá vì đó là những tuyến riêng, có gác cổng.
> Khi giá trị này là loopback, API ghi một cảnh báo lúc khởi động. Để nguyên
> nếu chấp nhận trích dẫn chỉ dùng trên máy chủ.
>
> ⚠️ **Quan trọng — `API_HOST=0.0.0.0` cũng mở `/v1/chat/completions` ra cả
> mạng LAN.** Tuyến này chấp nhận HOẶC một phiên đăng nhập hợp lệ (`/chat` của
> bạn tự động gửi kèm — không cần cấu hình gì) HOẶC `API_SHARED_SECRET` — nên
> một nhân viên đã đăng nhập `/chat` luôn gọi được, nhưng vẫn nên đặt
> `API_SHARED_SECRET` thành một chuỗi ngẫu nhiên (xem `.env.example`) để chặn
> một request HTTP trực tiếp, không có phiên đăng nhập, từ máy khác trong
> mạng. Hoặc giới hạn quyền truy cập cổng 8000 bằng tường lửa/router chỉ cho
> các máy trong công ty. API ghi một cảnh báo lúc khởi động nếu
> `API_HOST=0.0.0.0` mà chưa đặt `API_SHARED_SECRET`.

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
> liệu CÔNG KHAI vào đây** — tài liệu nội bộ nạp qua trang /admin như bình thường.
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
- **Frontend:** a single React app (`frontend/`), one process, one port — the
  landing page (`/`), a bespoke chat UI (`/chat`, self-hosted KaTeX, any
  signed-in account), and the admin console (`/admin`, admin role only). Open
  WebUI has been fully retired: no second login, no port 3000. One account
  system (email `@baoviet.com` + password, see step 6 above) gates both
  `/admin` and `/chat`, with role-based access — see RBAC below.

**Deployment is Docker-free** (company machines don't allow Docker): the
`scripts/*_native.sh` scripts run everything directly — the API in a local
venv (pandoc bundled via `pypandoc-binary`), and Qdrant **embedded in-process**
via qdrant-client local mode (`QDRANT_LOCAL_PATH` in `.env`; empty switches
back to server mode at `QDRANT_URL`). Only Python 3.11/3.12 and Ollama need to
be installed. See the deployment steps above (same commands). Development
uses `data/synthetic/` only; `data/real/` is confidential and never touched.

> Embedded-mode caveat: the storage directory is single-process. Stop the API
> (`bash scripts/stop_native.sh`) before running `eval/run_ragas.py` natively.

### Optional: Docker dev stack

`docker-compose.yml` still works for dev machines that have Docker
(`docker compose up -d`; add `docker-compose.gpu.yml` for an NVIDIA GPU).
The container always uses server-mode Qdrant — compose overrides
`QDRANT_LOCAL_PATH` internally — but `OLLAMA_BASE_URL` is substituted from
`.env`: delete that line from `.env` to use the in-compose `ollama` service,
or point it at `http://host.docker.internal:11434` for a native Ollama (next
section). The `api` container serves `/`, `/admin`, and `/chat` on its
mapped port same as native mode.

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
bash scripts/setup_native.sh                # one-time native setup (venv + models + frontend build)
bash scripts/run_native.sh                  # start the stack natively (no Docker)
bash scripts/stop_native.sh                 # stop it
bash scripts/setup_models.sh                # (re-)pull models — autodetects native vs docker
bash scripts/healthcheck.sh                 # smoke test
.venv/bin/python scripts/seed_accounts.py you@baoviet.com PASSWORD admin  # provision an account
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
a React admin console at `/admin` for system status / document upload/edit/
delete / quick testing, and a bespoke chat UI at `/chat` (self-hosted KaTeX,
citation source panel, real prompt suggestions) — see the Frontend section
above; Open WebUI has been fully retired (no more separate service, no more
port 3000 — its conversation history was not migrated);
role-based access on one account system (`app/accounts.py`): email
(`@baoviet.com`)+password accounts (`scripts/seed_accounts.py` provisions
them; no self-service signup) gate `/admin` (role `admin` only — enforced
server-side, e.g. `DELETE /documents/{id}` and `GET /documents` 403 for
`employee`) and `/chat` (either role) — bound to `127.0.0.1` via `API_HOST`
by default; an employee navigating straight to `/admin` is redirected to
`/chat`, and an admin's `/chat` sidebar links to `/admin`;
Docker-free native deployment (`scripts/setup_native.sh` / `run_native.sh` /
`stop_native.sh`, embedded in-process Qdrant via `QDRANT_LOCAL_PATH`, pandoc
bundled via `pypandoc-binary`) for company machines where Docker isn't allowed.

**Next:** scanned-document OCR (PaddleOCR + formula-OCR + figures), and
reranker latency reduction on CPU-only machines (measured ~50s/query on an
M1 CPU container — see the api logs' `retrieval timings`).

See `CLAUDE.md` for architecture and the non-negotiable security rules, and
`.claude/skills/insurance-rag-pipeline/SKILL.md` for the implementation guide.
