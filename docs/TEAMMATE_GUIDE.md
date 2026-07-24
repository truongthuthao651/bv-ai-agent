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

## Môi trường phát triển

Trên Windows dùng Git Bash. Cài Git for Windows, uv và Ollama, sau đó:

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
