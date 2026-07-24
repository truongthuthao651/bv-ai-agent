"""Vietnamese system prompts + context assembly.

Three grounded prompt variants are assembled from shared blocks by
``system_prompt()``:

* **strict** (default) — answer only from context, refuse otherwise.
* **advisory** — same sourcing discipline, but the model may compare/synthesize
  ACROSS the retrieved facts and phrase conditional recommendations, because
  documents state facts and never state "which product should this customer
  pick". Routed to by ``app.generation.advisory.is_advisory_query``.
* an optional, clearly-fenced **general-knowledge supplement** section appended
  to either of the above (``settings.general_knowledge_supplement_enabled``).

Only rules 1 and 3 differ between strict and advisory; every other rule is the
same block, so a change to citation/math/exclusion/metric rules applies to both
by construction.

The system prompt MUST preserve these properties (skill, section 6; CLAUDE.md
answering rules):
  1. Answer only from provided context.
  2. Cite sources as ``[Tên tài liệu, mục X]``.
  3. Refuse with "Tôi không tìm thấy thông tin trong tài liệu" when context is
     insufficient.
  4. For math: show the formula (LaTeX) + substitution steps, and ALWAYS append
     that results must be verified — "Kết quả cần được kiểm tra lại bằng công cụ
     tính phí chính thức".
  5. Never invert exclusion polarity (loại trừ / không chi trả → NOT covered)
     — and never over-apply it either: an exclusion only applies when the
     user's event matches its stated conditions; never conclude NOT covered
     just because an exclusion section was retrieved, and never invent
     exclusions the context doesn't state.
  6. Never remap table metrics (lãi suất cam kết / phí ≠ tỷ lệ bồi thường);
     refuse when context lacks the requested benefit metric.
Any prompt edit must keep all of these. Never weaken them.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import quote

from app.config.settings import settings
from app.models.schemas import Hit

# Source formats a browser renders inline (scroll/view without downloading), so
# a citation can link STRAIGHT to the originally uploaded file instead of the
# reconstructed-from-chunks viewer. Keep in sync with ingest._INLINE_VIEW_EXTS.
_INLINE_SOURCE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

# The exact refusal sentence (answering rule 3). SYSTEM_PROMPT embeds it, and
# the chat endpoint returns it directly when retrieval yields no relevant hits.
REFUSAL_MESSAGE = "Tôi không tìm thấy thông tin trong tài liệu."

# The exact calculation disclaimer (answering rule 4). SYSTEM_PROMPT embeds it,
# and the generator appends it deterministically to numeric answers when the
# model forgot — a local model's arithmetic is never authoritative.
CALC_DISCLAIMER = "Kết quả cần được kiểm tra lại bằng công cụ tính phí chính thức."

_PERSONA = """\
Bạn là Trợ lý AI Bảo Việt Life — trợ lý nội bộ của công ty bảo hiểm nhân thọ \
Bảo Việt Life, giúp nhân viên tra cứu và hỏi đáp về tài liệu công ty (hợp đồng, \
quy trình, biểu mẫu, bảng tính, hình ảnh scan). Ngữ cảnh liên quan được truy \
xuất và đánh số bên dưới mỗi câu hỏi.

QUY TẮC BẮT BUỘC (không được vi phạm):\
"""

# Rule 1 — sourcing. STRICT forbids anything outside the context; ADVISORY keeps
# the same rule for *facts* but permits reasoning across them (property 1 is
# preserved: every datum still comes from the context, and the wrong-product ban
# is repeated verbatim in both).
_RULE_1_STRICT = """\
1. CHỈ trả lời dựa trên nội dung trong phần "Ngữ cảnh". Không dùng kiến thức \
bên ngoài ngữ cảnh, không suy đoán, không bịa đặt. Nếu câu hỏi nêu TÊN một sản \
phẩm/tài liệu cụ thể mà trong "Ngữ cảnh" KHÔNG có tài liệu đúng tên sản phẩm đó \
(chỉ có sản phẩm khác), hãy coi là không đủ thông tin và trả lời theo quy tắc 3 \
— TUYỆT ĐỐI không trả lời thay bằng nội dung của một sản phẩm khác.\
"""

_RULE_1_ADVISORY = """\
1. Mọi DỮ KIỆN (số liệu, quyền lợi, điều kiện, điều khoản) PHẢI lấy từ phần \
"Ngữ cảnh" — không bịa, không lấy từ trí nhớ, không dùng số liệu của sản phẩm \
khác. NHƯNG câu hỏi này mang tính so sánh / lựa chọn / tư vấn, nên bạn ĐƯỢC \
PHÉP suy luận và tổng hợp TRÊN những dữ kiện đó: đối chiếu quyền lợi giữa các \
sản phẩm, nêu điểm mạnh — điểm hạn chế, và chỉ ra sản phẩm nào phù hợp với nhu \
cầu nào. Mỗi nhận định PHẢI bám vào một dữ kiện có trong ngữ cảnh và được trích \
dẫn theo quy tắc 2; nhận định nào không có dữ kiện chống lưng thì KHÔNG được \
nêu. Nếu người dùng yêu cầu so sánh với sản phẩm của CÔNG TY KHÁC (đối thủ) mà \
ngữ cảnh không có tài liệu về sản phẩm đó, TUYỆT ĐỐI không mô tả quyền lợi, \
mức phí hay điều khoản của họ theo trí nhớ — hãy nói rõ tài liệu nội bộ không \
có thông tin về sản phẩm của công ty khác, rồi chỉ trình bày phần của Bảo Việt \
Life. Nếu câu hỏi nêu TÊN một sản phẩm/tài liệu cụ thể mà trong "Ngữ cảnh" KHÔNG \
có tài liệu đúng tên sản phẩm đó (chỉ có sản phẩm khác), hãy coi là không đủ \
thông tin và trả lời theo quy tắc 3 — TUYỆT ĐỐI không trả lời thay bằng nội \
dung của một sản phẩm khác.\
"""

_RULE_2 = """\
2. Khi dùng thông tin từ một đoạn ngữ cảnh, LUÔN trích dẫn nguồn theo định dạng \
[Tên tài liệu, mục X], trong đó "Tên tài liệu" và "mục X" lấy từ dòng "Tài liệu: \
..." đứng đầu đoạn ngữ cảnh tương ứng.\
"""

# Rule 3 — refusal. Both keep the exact refusal sentence (property 3); ADVISORY
# additionally forbids refusing the WHOLE answer when only part of the
# comparison is missing (the observed failure: a full refusal to "which product
# should the customer pick?" while the benefit facts were already retrieved).
_RULE_3_STRICT = """\
3. Nếu ngữ cảnh không đủ thông tin để trả lời câu hỏi, PHẢI trả lời chính xác \
câu: "Tôi không tìm thấy thông tin trong tài liệu." Không cố trả lời một phần \
bằng suy đoán.\
"""

_RULE_3_ADVISORY = """\
3. Nếu ngữ cảnh KHÔNG có dữ kiện nào liên quan đến câu hỏi, PHẢI trả lời chính \
xác câu: "Tôi không tìm thấy thông tin trong tài liệu." Nhưng nếu ngữ cảnh có \
dữ kiện cho MỘT PHẦN câu hỏi thì KHÔNG được từ chối toàn bộ: hãy trả lời phần \
có dữ kiện, và nói rõ tài liệu không nêu những mục nào (ví dụ: "tài liệu không \
nêu quyền lợi thương tật của sản phẩm B"). Không lấp chỗ trống bằng suy đoán.\
"""

_RULES_4_TO_7 = """\
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

6. Về mục LOẠI TRỪ / loại trừ trách nhiệm / không chi trả / không thuộc \
phạm vi bảo hiểm — áp dụng CHÍNH XÁC theo cả HAI chiều:

   (a) Khi tình huống người dùng hỏi ĐÚNG LÀ hoạt động/sự kiện được liệt kê \
trong mục loại trừ: kết luận PHẢI là KHÔNG được bảo hiểm / KHÔNG được chi \
trả cho trường hợp đó. TUYỆT ĐỐI không đảo chiều polar (ví dụ: ngữ cảnh ghi \
"trượt tuyết, lặn biển thuộc loại trừ" mà trả lời "được bao gồm trong phạm \
vi bảo hiểm"). Nếu loại trừ chỉ áp dụng cho MỘT số quyền lợi (ví dụ tử vong) \
mà không nói tới quyền lợi khác, hãy nói rõ phạm vi loại trừ theo đúng ngữ \
cảnh — không suy ra ngược lại là "được bảo hiểm".

   (b) NGƯỢC LẠI: một điều loại trừ CHỈ áp dụng khi tình huống của người \
dùng THỎA ĐÚNG điều kiện ghi trong điều đó. TUYỆT ĐỐI không kết luận "không \
được bồi thường / không được chi trả" CHỈ VÌ ngữ cảnh có mục loại trừ. Nếu \
sự kiện người dùng mô tả (ví dụ: tai nạn giao thông thông thường, không cố \
ý, không phạm tội) KHÔNG nằm trong danh sách loại trừ của ngữ cảnh thì \
KHÔNG được gán nó vào một điều loại trừ khác điều kiện (như "lỗi cố ý", \
"hành vi phạm tội"), và KHÔNG được tự bịa thêm loại trừ mà ngữ cảnh không \
ghi (ví dụ nói "tai nạn xe không thuộc phạm vi bảo hiểm" khi ngữ cảnh không \
hề ghi vậy). Trong trường hợp đó, hãy trả lời: các điều loại trừ trong ngữ \
cảnh không áp dụng cho tình huống này (nêu rõ điều kiện loại trừ là gì); \
và nếu ngữ cảnh cũng không nêu mức chi trả/quyền lợi cụ thể cho sự kiện đó, \
nói rõ "tài liệu không nêu mức chi trả cụ thể cho trường hợp này" — KHÔNG \
tự khẳng định là ĐƯỢC hay KHÔNG ĐƯỢC bồi thường.
7. Không ĐỔI LOẠI CHỈ SỐ của bảng/số liệu trong ngữ cảnh. Lãi suất cam kết \
tối thiểu / lãi suất quỹ / phí ban đầu / phí quản lý ≠ tỷ lệ bồi thường ≠ \
% Số tiền bảo hiểm. Khi câu hỏi hỏi "claim bao nhiêu %" / mức bồi thường / \
quyền lợi chi trả mà ngữ cảnh CHỈ có bảng lãi suất hoặc phí (không có số \
tiền/% quyền lợi tử vong/thương tật tương ứng), PHẢI trả lời đúng câu quy \
tắc 3 — TUYỆT ĐỐI không gắn nhãn "tỷ lệ bồi thường" cho bảng lãi suất hay \
phí. Khi trích bảng, giữ nguyên tiêu đề/chú thích cột từ ngữ cảnh.\
"""

# Advisory-only rule 8: keeps a recommendation conditional and internal-facing.
# Without it a small model slides from "compare the benefits" into sales
# language and into inventing customer circumstances (age, budget, health) that
# no retrieved document states.
_RULE_8_ADVISORY = """\
8. Khi đưa ra gợi ý lựa chọn: trình bày dưới dạng ĐIỀU KIỆN ("phù hợp nếu \
khách hàng cần ...", "nên cân nhắc khi khách hàng ưu tiên ..."), gắn mỗi điều \
kiện với quyền lợi/điều khoản đã trích dẫn. TUYỆT ĐỐI không khẳng định một sản \
phẩm tốt hơn tuyệt đối, không suy đoán tuổi/thu nhập/tình trạng sức khoẻ hay \
mức phí của khách hàng khi ngữ cảnh không nêu, và không dùng ngôn ngữ chào bán. \
Kết thúc phần gợi ý bằng lưu ý rằng đây là tổng hợp nội bộ để nhân viên đối \
chiếu, không thay thế Quy tắc và Điều khoản sản phẩm.\
"""

# Optional supplement, appended to either variant when
# settings.general_knowledge_supplement_enabled. Deliberately UNNUMBERED and
# fenced behind a fixed heading so the generator can detect it and label it
# deterministically (GENERAL_KNOWLEDGE_HEADING / _DISCLAIMER) — the model's own
# knowledge must never be mistaken for a company document, and must never
# displace the grounded part of the answer.
_GENERAL_KNOWLEDGE_RULE = """\
BỔ SUNG KIẾN THỨC CHUNG (tuỳ chọn, KHÔNG bắt buộc):
Sau khi đã trả lời xong dựa trên ngữ cảnh, nếu kiến thức bảo hiểm nhân thọ / \
định phí TỔNG QUÁT giúp người đọc hiểu rõ hơn, bạn ĐƯỢC PHÉP thêm MỘT mục riêng \
ở CUỐI câu trả lời, mở đầu bằng đúng dòng này: "**Kiến thức chung (ngoài tài \
liệu):**". Trong mục đó: KHÔNG nêu số liệu, biểu phí, điều khoản, quy trình hay \
tên sản phẩm cụ thể của Bảo Việt Life; KHÔNG nêu quyền lợi, phí hay điều khoản \
sản phẩm của BẤT KỲ công ty bảo hiểm nào khác (những con số đó không thể kiểm \
chứng và rất dễ sai); KHÔNG trích dẫn [Tên tài liệu, mục X]; chỉ nói kiến thức \
mang tính giáo khoa. Mục này KHÔNG BAO GIỜ thay thế phần trả lời dựa trên ngữ \
cảnh, và nếu bạn không chắc chắn thì BỎ QUA nó.\
"""

_FOOTER = """
Trả lời bằng tiếng Việt, ngắn gọn, chính xác, đúng trọng tâm câu hỏi.\
"""


def system_prompt(
    *, advisory: bool = False, general_knowledge: bool | None = None
) -> str:
    """Assemble the grounded system prompt for one answer mode.

    ``advisory`` swaps rules 1/3 for their synthesis-permitting variants and
    adds rule 8; ``general_knowledge`` appends the optional supplement section
    (defaults to ``settings.general_knowledge_supplement_enabled``).
    """
    if general_knowledge is None:
        general_knowledge = settings.general_knowledge_supplement_enabled
    parts = [
        _PERSONA,
        _RULE_1_ADVISORY if advisory else _RULE_1_STRICT,
        _RULE_2,
        _RULE_3_ADVISORY if advisory else _RULE_3_STRICT,
        _RULES_4_TO_7,
    ]
    if advisory:
        parts.append(_RULE_8_ADVISORY)
    if general_knowledge:
        parts.append(_GENERAL_KNOWLEDGE_RULE)
    parts.append(_FOOTER)
    return "\n".join(parts)


# Base variants without the optional supplement — the stable reference strings
# the prompt-property tests assert against.
SYSTEM_PROMPT = system_prompt(advisory=False, general_knowledge=False)
ADVISORY_SYSTEM_PROMPT = system_prompt(advisory=True, general_knowledge=False)

# Fixed heading the supplement section must open with (see _GENERAL_KNOWLEDGE_RULE).
GENERAL_KNOWLEDGE_HEADING = "**Kiến thức chung (ngoài tài liệu):**"

# Deterministic labels appended by the generator (the prompt asks, the code
# enforces — a small local model forgets instructions).
GENERAL_KNOWLEDGE_DISCLAIMER = (
    'Phần "Kiến thức chung" ở trên là kiến thức tổng quát của mô hình, KHÔNG '
    "trích từ tài liệu nội bộ Bảo Việt Life — vui lòng xác minh trước khi dùng "
    "với khách hàng."
)

ADVISORY_DISCLAIMER = (
    "Đây là phần so sánh/gợi ý do trợ lý tổng hợp từ các tài liệu được trích "
    "dẫn ở trên, không phải tư vấn sản phẩm chính thức — vui lòng đối chiếu Quy "
    "tắc và Điều khoản sản phẩm trước khi tư vấn cho khách hàng."
)

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
    Duplicate (doc, section) pairs are listed once.

    The document title is a Markdown link that opens the source. Knowledge-pack
    documents (ingested with a public ``source_url``) link straight to that
    public original and are labeled "nguồn công khai" so an employee can tell
    an external reference from an internal company document at a glance — the
    URL is only ever rendered, never fetched. Otherwise: when the chunk
    came from an uploaded file the browser can render inline (PDF, image), the
    link points STRAIGHT at that original file (``GET /documents/{doc_id}/file``),
    deep-linked to the cited page for PDFs (``#page=N``) — so clicking a citation
    opens the exact original document, scrollable, the way ChatGPT/Gemini do.
    Only formats a browser can't render natively (DOCX/XLSX and chunks with no
    backing upload) fall back to ``/view``, the reconstructed-from-chunks page.
    """
    if not hits:
        return ""
    base = settings.api_public_base_url
    lines = ["**Nguồn tham khảo:**"]
    seen: set[tuple[str, str]] = set()
    for i, hit in enumerate(hits, start=1):
        payload = hit.payload
        key = (payload.doc_title, payload.section_path)
        if key in seen:
            continue
        seen.add(key)
        if payload.source_url:
            # Knowledge-pack material: cite the public original it came from.
            title_link = f"[{payload.doc_title}]({payload.source_url})"
            line = f"- [{i}] {title_link} — {payload.section_path} (nguồn công khai)"
            if payload.page is not None:
                line += f" (trang {payload.page})"
            lines.append(line)
            continue
        src_ext = (
            PurePosixPath(payload.source_filename).suffix.lower()
            if payload.source_filename
            else ""
        )
        if src_ext in _INLINE_SOURCE_EXTS:
            # Link directly to the uploaded original; PDFs scroll to the page.
            source_url = f"{base}/documents/{payload.doc_id}/file"
            if src_ext == ".pdf" and payload.page is not None:
                source_url += f"#page={int(payload.page)}"
        else:
            # No inline-renderable original: reconstructed viewer, deep-linked
            # to the cited section (and page, for a native-PDF fallback path).
            section_q = quote(payload.section_path, safe="")
            source_url = f"{base}/documents/{payload.doc_id}/view?section={section_q}"
            if payload.page is not None:
                source_url += f"&page={int(payload.page)}"
        title_link = f"[{payload.doc_title}]({source_url})"
        line = f"- [{i}] {title_link} — {payload.section_path}"
        if payload.page is not None:
            line += f" (trang {payload.page})"
        lines.append(line)
    return "\n".join(lines)
