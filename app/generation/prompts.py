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

from app.models.schemas import Hit

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
tra lại bằng công cụ tính phí chính thức."

Trả lời bằng tiếng Việt, ngắn gọn, chính xác, đúng trọng tâm câu hỏi.\
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
