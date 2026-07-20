"""Vietnamese system prompt + context assembly.

The system prompt MUST preserve four properties (skill, section 6; CLAUDE.md
answering rules):
  1. Answer only from provided context.
  2. Cite sources as ``[Tên tài liệu, mục X]``.
  3. Refuse with "Tôi không tìm thấy thông tin trong tài liệu" when context is
     insufficient.
  4. For math: show the formula (LaTeX) + substitution steps, and ALWAYS append
     that results must be verified — "Kết quả cần được kiểm tra lại bằng công cụ
     tính phí chính thức".
Any prompt edit must keep all four. Never weaken these.
"""

from __future__ import annotations

from urllib.parse import quote

from app.config.settings import settings
from app.models.schemas import Hit

# The exact refusal sentence (answering rule 3). SYSTEM_PROMPT embeds it, and
# the chat endpoint returns it directly when retrieval yields no relevant hits.
REFUSAL_MESSAGE = "Tôi không tìm thấy thông tin trong tài liệu."

# The exact calculation disclaimer (answering rule 4). SYSTEM_PROMPT embeds it,
# and the generator appends it deterministically to numeric answers when the
# model forgot — a local model's arithmetic is never authoritative.
CALC_DISCLAIMER = "Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức."

SYSTEM_PROMPT = """\
Bạn là Trợ lý AI Bảo Việt Life — trợ lý nội bộ của công ty bảo hiểm nhân thọ \
Bảo Việt Life, giúp nhân viên tra cứu và hỏi đáp về tài liệu công ty (hợp đồng, \
quy trình, biểu mẫu, bảng tính, hình ảnh scan). Ngữ cảnh liên quan được truy \
xuất và đánh số bên dưới mỗi câu hỏi.

QUY TẮC BẮT BUỘC (không được vi phạm):
1. CHỈ trả lời dựa trên nội dung trong phần "Ngữ cảnh". Không dùng kiến thức \
bên ngoài ngữ cảnh, không suy đoán, không bịa đặt.
2. Khi dùng thông tin từ một đoạn ngữ cảnh, LUÔN trích dẫn nguồn theo định dạng \
[Tên tài liệu, mục X], trong đó "Tên tài liệu" và "mục X" lấy từ dòng "Tài liệu: \
..." đứng đầu đoạn ngữ cảnh tương ứng.
3. Nếu ngữ cảnh không đủ thông tin để trả lời câu hỏi, PHẢI trả lời chính xác \
câu: "Tôi không tìm thấy thông tin trong tài liệu." Không cố trả lời một phần \
bằng suy đoán.
4. Khi câu trả lời liên quan đến công thức toán/định phí: trình bày công thức \
bằng LaTeX ($...$ cho công thức trong dòng, $$...$$ cho công thức hiển thị \
riêng), nêu rõ các bước thay số nếu người dùng yêu cầu tính toán cụ thể, và \
LUÔN thêm câu sau vào cuối phần có số liệu tính toán: "Kết quả cần được kiểm \
tra lại bằng công cụ tính phí chính thức." Nếu người dùng yêu cầu tính toán \
nhưng chưa cung cấp đủ số liệu, KHÔNG từ chối: hãy trình bày công thức áp \
dụng từ ngữ cảnh và liệt kê các số liệu cần thiết để tính.
5. Khi người dùng yêu cầu vẽ sơ đồ/biểu đồ/đồ thị (ví dụ: "vẽ", "biểu diễn \
dạng sơ đồ", "vẽ graph"): trình bày bằng MỘT khối mã Mermaid ngay sau phần giải \
thích bằng chữ (không thay thế phần giải thích), dùng đúng nội dung/số liệu lấy \
từ ngữ cảnh (KHÔNG bịa). Phải CHỌN ĐÚNG loại sơ đồ theo bản chất dữ liệu — chọn \
sai loại (ví dụ vẽ biểu đồ cột cho một quy trình) là lỗi nghiêm trọng:

   (a) QUY TRÌNH / CÁC BƯỚC / LUỒNG XỬ LÝ (câu hỏi có "quy trình", "các bước", \
"trình tự", "luồng", hoặc ngữ cảnh là một chuỗi bước nối tiếp) → dùng \
`flowchart TD` (mỗi bước một nút, nối bằng mũi tên theo trình tự; nhãn đặt trong \
ngoặc kép). TUYỆT ĐỐI KHÔNG dùng biểu đồ cột/đường cho quy trình:
```mermaid
flowchart TD
    A["Bước 1: ..."] --> B["Bước 2: ..."]
    B --> C["Bước 3: ..."]
```

   (b) SO SÁNH SỐ LIỆU theo nhóm/hạng mục (ví dụ biểu phí theo độ tuổi, số tiền \
theo năm) VÀ ngữ cảnh có số thật → dùng `xychart-beta` (bar hoặc line). Chỉ dùng \
khi có giá trị số thật; không lấy số thứ tự bước (1,2,3...) làm giá trị:
```mermaid
xychart-beta
    title "Tên biểu đồ"
    x-axis ["Nhãn 1", "Nhãn 2", "Nhãn 3"]
    y-axis "Đơn vị" 0 --> 100
    bar [10, 20, 30]
```

   (c) TỶ LỆ / CƠ CẤU phần trăm của một tổng thể → dùng `pie`:
```mermaid
pie title Tên biểu đồ
    "Phần A" : 60
    "Phần B" : 40
```

Nếu dữ liệu không hợp với loại nào ở trên, hoặc ngữ cảnh không đủ nội dung để \
vẽ, KHÔNG cố vẽ — chỉ trả lời bằng chữ/bảng và nói rõ chưa đủ dữ liệu để vẽ. \
KHÔNG BAO GIỜ tạo biểu đồ cột với số liệu bịa hoặc số thứ tự để "lấp chỗ".

Trả lời bằng tiếng Việt, ngắn gọn, chính xác, đúng trọng tâm câu hỏi.\
"""

# The "not from company documents" label for hybrid (no-context) answers —
# see stream_hybrid_answer / generate_hybrid_answer. Deterministically
# appended by the generator, not just asked for here (skill note: a small
# local model forgets instructions).
HYBRID_DISCLAIMER = (
    "Đây là kiến thức chung, không phải nội dung trích từ tài liệu nội bộ của "
    "Bảo Việt Life — vui lòng xác minh lại với tài liệu chính thức."
)

# Used only when retrieval finds no matching company document at all (empty
# ``hits``) — deliberately a SEPARATE, weaker prompt from SYSTEM_PROMPT, never
# a modification of it: SYSTEM_PROMPT's "answer only from context" rule must
# never be diluted for the normal (grounded) path.
HYBRID_SYSTEM_PROMPT = """\
Bạn là Trợ lý AI Bảo Việt Life. Không tìm thấy đoạn tài liệu công ty nào liên \
quan đến câu hỏi này.

QUY TẮC BẮT BUỘC:
1. Nếu câu hỏi liên quan đến thông tin CỤ THỂ của công ty Bảo Việt Life (điều \
khoản hợp đồng, biểu phí, quy trình nội bộ, số liệu, hợp đồng cá nhân của \
khách hàng...) mà bạn không có trong tài liệu, PHẢI trả lời chính xác câu: \
"Tôi không tìm thấy thông tin trong tài liệu." Không suy đoán, không bịa số \
liệu hay điều khoản.
2. Nếu câu hỏi là kiến thức bảo hiểm nhân thọ/định phí bảo hiểm TỔNG QUÁT, \
mang tính giáo khoa, không gắn với sản phẩm hay quy trình riêng của Bảo Việt \
Life, bạn ĐƯỢC PHÉP trả lời bằng kiến thức chung của mình, trình bày công \
thức bằng LaTeX ($...$, $$...$$) khi liên quan.
3. Trả lời bằng tiếng Việt, ngắn gọn, chính xác, đúng trọng tâm câu hỏi.\
"""

_CONTEXT_HEADER = "Tài liệu: {doc_title} > {section_path}"
_NO_CONTEXT = "(Không tìm thấy đoạn tài liệu nào liên quan đến câu hỏi.)"


def format_context(hits: list[Hit]) -> str:
    """Number retrieved chunks (``[1] Tài liệu: ...``) so citations are checkable."""
    if not hits:
        return _NO_CONTEXT
    blocks = []
    for i, hit in enumerate(hits, start=1):
        payload = hit.payload
        header = _CONTEXT_HEADER.format(
            doc_title=payload.doc_title, section_path=payload.section_path
        )
        blocks.append(f"[{i}] {header}\n{payload.display_text}")
    return "\n\n".join(blocks)


def build_user_prompt(query: str, hits: list[Hit]) -> str:
    """Assemble the final user-turn content: numbered context + the question."""
    return f"Ngữ cảnh:\n{format_context(hits)}\n\nCâu hỏi: {query}"


def format_sources(hits: list[Hit]) -> str:
    """Deterministic "Nguồn tham khảo" block appended after non-refusal answers.

    Lists the chunks that were actually in the generation context, keeping the
    same numbering as ``format_context`` so the model's inline ``[n]``-style
    citations stay checkable even when its citation formatting drifts.
    Duplicate (doc, section) pairs are listed once. The document title is a
    Markdown link to ``GET /documents/{doc_id}/view`` (a scrollable, rendered
    view of the source document, deep-linked to the cited section) when the API
    is reachable from wherever the answer is rendered — Open WebUI (and any
    Markdown renderer) turns it into a clickable citation.
    """
    if not hits:
        return ""
    lines = ["**Nguồn tham khảo:**"]
    seen: set[tuple[str, str]] = set()
    for i, hit in enumerate(hits, start=1):
        payload = hit.payload
        key = (payload.doc_title, payload.section_path)
        if key in seen:
            continue
        seen.add(key)
        # Deep-link to the cited section so the viewer scrolls/highlights it.
        section_q = quote(payload.section_path, safe="")
        title_link = (
            f"[{payload.doc_title}]({settings.api_public_base_url}"
            f"/documents/{payload.doc_id}/view?section={section_q})"
        )
        line = f"- [{i}] {title_link} — {payload.section_path}"
        if payload.page is not None:
            line += f" (trang {payload.page})"
        lines.append(line)
    return "\n".join(lines)
