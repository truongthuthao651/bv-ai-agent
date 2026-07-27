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
> # Windows Git Bash:
> .venv/Scripts/python.exe scripts/ingest_knowledge_pack.py --dry-run
> .venv/Scripts/python.exe scripts/ingest_knowledge_pack.py
> # macOS/Linux:
> .venv/bin/python scripts/ingest_knowledge_pack.py --dry-run
> .venv/bin/python scripts/ingest_knowledge_pack.py
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

Common native commands:

```bash
bash scripts/setup_native.sh                # one-time native setup (venvs + all models)
bash scripts/run_native.sh                  # start Ollama, FastAPI/Qdrant, and Open WebUI
bash scripts/stop_native.sh                 # stop it
bash scripts/setup_models.sh                # (re-)pull local models
bash scripts/healthcheck.sh                 # smoke test
```

For Python commands, use `.venv/Scripts/python.exe` on Windows Git Bash or
`.venv/bin/python` on macOS/Linux. For example, after stopping the API:

```bash
# Windows Git Bash
.venv/Scripts/python.exe scripts/ingest_knowledge_pack.py --dry-run
.venv/Scripts/python.exe eval/run_ragas.py

# macOS/Linux
.venv/bin/python scripts/ingest_knowledge_pack.py --dry-run
.venv/bin/python eval/run_ragas.py
```

### Project status

Implemented: native deployment, embedded Qdrant, document ingestion for
Markdown/DOCX/XLSX/PDF/glossary files, hybrid retrieval with reranking, cited
streaming answers, Open WebUI integration, administration, RBAC, and offline
evaluation. Planned improvements include scanned-document OCR and CPU reranker
latency reduction.
