# Trợ lý AI Bảo Việt Life — RAG nội bộ cho tài liệu công ty

> **Local RAG Assistant for a Vietnamese Life Insurance Firm** — English section below.

Trợ lý AI chạy hoàn toàn nội bộ để nhân viên tra cứu và hỏi đáp về tài liệu
công ty: hợp đồng, quy trình, biểu mẫu, bảng tính và ảnh scan. Câu trả lời
bằng tiếng Việt, có trích dẫn nguồn và hiển thị công thức LaTeX. Dữ liệu không
rời khỏi máy chủ và ứng dụng không gọi API bên ngoài.

- **Mô hình:** Ollama — chat `qwen3:8b`, thị giác `qwen2.5vl:7b`
- **Tìm kiếm:** Qdrant nhúng trong FastAPI, bge-m3 và bge-reranker-v2-m3
- **Giao diện:** Open WebUI trỏ tới API FastAPI cục bộ

> **Bảo mật:** Không đưa `data/real/` vào Git và không dùng nó trong phát
> triển hoặc kiểm thử. Chỉ dùng `data/synthetic/`.

---

## Triển khai trên máy công ty

Hệ thống chạy trực tiếp trên máy, không cần nền tảng ảo hóa. Trên Windows, mở
**Git Bash** để chạy các lệnh bên dưới; PowerShell không chạy tệp `.sh` trực
tiếp. Cần cài một lần:

1. [Git for Windows](https://git-scm.com/download/win) (bao gồm Git Bash)
2. [uv](https://docs.astral.sh/uv/)
3. [Ollama](https://ollama.com)

UV tự tải Python 3.12 khi cần. Nếu UV không có, `setup_native.sh` tự chuyển
sang Python 3.11 hoặc 3.12 với `venv` và `pip`.

```bash
# 1) Lấy mã nguồn
git clone <repo-url> bv-ai-agent
cd bv-ai-agent

# 2) Tạo cấu hình riêng cho máy này
cp .env.example .env
# Có thể đổi CHAT_MODEL=qwen3:4b trên máy yếu, hoặc đổi các cổng nếu bị trùng.
# Đặt ADMIN_PASSWORD nếu máy chủ có người khác sử dụng.

# 3) Cài đặt một lần: môi trường Python, thư viện và các model
# Cần Internet ở bước này.
bash scripts/setup_native.sh

# 4) Khởi động hệ thống
bash scripts/run_native.sh

# 5) Kiểm tra sức khỏe
bash scripts/healthcheck.sh
```

Sau khi khởi động:

- Giao diện trò chuyện: <http://localhost:3000>
- Trang quản trị cục bộ: <http://localhost:8000>
- API sức khỏe: <http://localhost:8000/health>

Dừng hệ thống bằng `bash scripts/stop_native.sh`. Nhật ký nằm trong `logs/`.

Lần đầu mở Open WebUI, hãy tạo tài khoản đầu tiên; tài khoản này trở thành
admin. Admin tạo tài khoản nhân viên trong **Admin Panel → Users**, và chỉ công
khai model `bao-viet-life` cho người dùng thường. Giữ `WEBUI_AUTH=true` sau khi
đã có tài khoản.

### Lệnh thường dùng

```bash
bash scripts/setup_models.sh             # tải lại model khi cần Internet
bash scripts/ingest.sh data/synthetic     # nạp dữ liệu mẫu
bash scripts/ingest.sh data/glossary      # nạp bảng thuật ngữ
bash scripts/healthcheck.sh               # kiểm tra Ollama, API/Qdrant, WebUI
bash scripts/stop_native.sh               # dừng các tiến trình do script tạo
```

Chạy kiểm thử hoặc đánh giá bằng Python trong môi trường ứng dụng. Trên Git
Bash/Windows dùng `.venv/Scripts/python.exe`; trên macOS/Linux dùng
`.venv/bin/python`.

```bash
# Windows Git Bash
.venv/Scripts/python.exe -m pytest tests/ -x -q
.venv/Scripts/python.exe eval/run_ragas.py

# macOS/Linux
.venv/bin/python -m pytest tests/ -x -q
.venv/bin/python eval/run_ragas.py
```

Qdrant chạy nhúng trong API, vì vậy phải dừng API trước khi chạy
`eval/run_ragas.py`.

### Thiết lập không dùng UV

Khi UV không có trên PATH, cùng lệnh `bash scripts/setup_native.sh` sẽ tìm
Python 3.11 hoặc 3.12, tạo hai môi trường cục bộ và dùng `pip`. Không cần đổi
lệnh khởi động, kiểm tra sức khỏe hoặc dừng hệ thống.

---

## English

This is a fully local, offline assistant for company documents. It answers in
Vietnamese, includes source citations, renders LaTeX math, and does not send
company data to external APIs.

### Company deployment

Run the shell scripts in **Git Bash** on Windows. On macOS/Linux, run them in
your normal Bash-compatible terminal. Install Git for Windows (Windows only),
[uv](https://docs.astral.sh/uv/), and [Ollama](https://ollama.com), then run:

```bash
git clone <repo-url> bv-ai-agent
cd bv-ai-agent
cp .env.example .env
bash scripts/setup_native.sh
bash scripts/run_native.sh
bash scripts/healthcheck.sh
```

The setup script prefers UV and manages Python 3.12. When UV is not available,
it automatically falls back to an installed Python 3.11/3.12 plus `venv` and
`pip`. It installs the app and Open WebUI into separate local environments,
downloads required model weights, and applies the Bảo Việt branding.

Open <http://localhost:3000> for chat and <http://localhost:8000> for the
machine-local admin page. Stop the stack with `bash scripts/stop_native.sh`.

`QDRANT_LOCAL_PATH` keeps Qdrant embedded in the API process. The storage is
single-process, so stop the API before running `eval/run_ragas.py`.

### Security and operations

- Use `data/synthetic/` for development and tests; never inspect or commit
  `data/real/`.
- Configure machine-specific values only in `.env`.
- Network access is needed only while installing packages or downloading models;
  normal operation is local and offline.
- Keep `WEBUI_AUTH=true` once Open WebUI user accounts exist.

### Project status

Implemented: native deployment, embedded Qdrant, document ingestion for
Markdown/DOCX/XLSX/PDF/glossary files, hybrid retrieval with reranking, cited
streaming answers, Open WebUI integration, administration, RBAC, and offline
evaluation. Planned improvements include scanned-document OCR and CPU reranker
latency reduction.
