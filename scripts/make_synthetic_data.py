"""Generate a small synthetic Vietnamese insurance corpus for dev/testing.

Writes fake documents to ``data/synthetic/`` ONLY. Everything here is invented —
company names, product names, policy numbers, and amounts are all fictional; the
actuarial formulas are textbook-standard (life contingencies) and therefore not
confidential. See the insurance-rag-pipeline skill, section 7, and the security
rules in CLAUDE.md.

Emits Markdown (the canonical format), a claims-payout XLSX exercising the
spreadsheet path (multi-sheet, dates, VND amounts), and a text-layer PDF
exercising the Docling path (requires ``reportlab``, dev-time only). A DOCX
(real OMML equations) and scanned/figure samples arrive with the OCR increment.

Run:
    python scripts/make_synthetic_data.py
"""

from __future__ import annotations

import unicodedata
from datetime import date
from pathlib import Path

# Repo-relative output dir (this script runs on the host, not in the container,
# so we do not use application settings paths here).
SYNTHETIC_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"


# --------------------------------------------------------------------------- #
# Fake documents (Markdown + LaTeX). All content invented; formulas textbook.
# --------------------------------------------------------------------------- #

POLICY_TERM_LIFE = """\
# Quy tắc, Điều khoản Sản phẩm Bảo hiểm Tử kỳ "An Tâm Bảo Vệ"

Mã sản phẩm: ATBV-2025 (sản phẩm giả định phục vụ kiểm thử).

## Chương I: Quy định chung

### Điều 1: Định nghĩa

Trong bản Quy tắc này, các thuật ngữ dưới đây được hiểu như sau:

1. **Người được bảo hiểm** là cá nhân được chấp nhận bảo hiểm theo Hợp đồng.
2. **Số tiền bảo hiểm** là số tiền Công ty chi trả khi xảy ra sự kiện bảo hiểm.
3. **Phí bảo hiểm** là khoản tiền Bên mua bảo hiểm đóng theo định kỳ.

### Điều 2: Phạm vi bảo hiểm

Công ty chi trả Số tiền bảo hiểm nếu Người được bảo hiểm tử vong trong Thời hạn
hợp đồng, với điều kiện Hợp đồng đang có hiệu lực.

## Chương II: Phí bảo hiểm

### Điều 5: Nguyên tắc tính phí thuần

Phí thuần năm cho hợp đồng bảo hiểm tử kỳ $n$ năm, tuổi $x$, số tiền bảo hiểm 1
đơn vị, được xác định theo nguyên tắc cân bằng giá trị hiện tại:

$$P_{x:\\overline{n}|}^{1} = \\frac{A_{x:\\overline{n}|}^{1}}{\\ddot{a}_{x:\\overline{n}|}}$$

trong đó:

- $A_{x:\\overline{n}|}^{1}$ là giá trị hiện tại của quyền lợi tử vong trong $n$ năm;
- $\\ddot{a}_{x:\\overline{n}|}$ là niên kim nhân thọ tạm thời trả đầu kỳ trong $n$ năm;
- $P_{x:\\overline{n}|}^{1}$ là phí thuần năm.

### Điều 6: Đóng phí

Bên mua bảo hiểm đóng phí theo năm, nửa năm, quý hoặc tháng. Thời gian gia hạn
đóng phí là 60 ngày kể từ ngày đến hạn.
"""

DOC_RESERVES = """\
# Hướng dẫn Tính Dự phòng Toán học (tài liệu nội bộ giả định)

## Điều 1: Khái niệm dự phòng toán học

Dự phòng toán học tại thời điểm $t$ là chênh lệch giữa giá trị hiện tại của các
nghĩa vụ tương lai của Công ty và giá trị hiện tại của phí thuần tương lai.

## Điều 2: Công thức dự phòng theo phương pháp phí thuần

Đối với hợp đồng bảo hiểm trọn đời, tuổi phát hành $x$, dự phòng tại thời điểm
$t$ (phương pháp phí thuần) là:

$$_{t}V_{x} = A_{x+t} - P_{x} \\cdot \\ddot{a}_{x+t}$$

trong đó:

- $_{t}V_{x}$ là dự phòng toán học tại thời điểm $t$;
- $A_{x+t}$ là giá trị hiện tại của bảo hiểm trọn đời tại tuổi $x+t$;
- $P_{x}$ là phí thuần năm của hợp đồng trọn đời phát hành ở tuổi $x$;
- $\\ddot{a}_{x+t}$ là niên kim nhân thọ trọn đời trả đầu kỳ tại tuổi $x+t$.

## Điều 3: Hệ số chiết khấu

Hệ số chiết khấu một năm được tính từ lãi suất kỹ thuật $i$:

$$v = \\frac{1}{1+i}$$

Với lãi suất kỹ thuật giả định $i = 0{,}05$ thì $v \\approx 0{,}952$.
"""

ANNUITY_MORTALITY = """\
# Hướng dẫn Tính Niên kim Nhân thọ và Sử dụng Bảng Tỷ lệ Tử vong (tài liệu nội bộ giả định)

## Điều 1: Bảng tỷ lệ tử vong minh họa

Bảng dưới đây minh họa số người còn sống $l_x$ tại một số độ tuổi (số liệu giả
định phục vụ kiểm thử):

| Tuổi $x$ | $l_x$ | $q_x$ |
| --- | --- | --- |
| 30 | 970000 | 0,00120 |
| 31 | 968836 | 0,00125 |
| 32 | 967625 | 0,00131 |
| 33 | 966358 | 0,00138 |
| 34 | 965024 | 0,00145 |

Xác suất tử vong $q_x$ và xác suất sống $p_x$ tại tuổi $x$ liên hệ với bảng tỷ
lệ tử vong theo công thức:

$$q_x = \\frac{l_x - l_{x+1}}{l_x}, \\qquad p_x = 1 - q_x = \\frac{l_{x+1}}{l_x}$$

trong đó:

- $l_x$ là số người còn sống ở tuổi $x$ trong bảng tỷ lệ tử vong;
- $q_x$ là xác suất một người tuổi $x$ tử vong trước khi đạt tuổi $x+1$;
- $p_x$ là xác suất một người tuổi $x$ sống đến tuổi $x+1$.

## Điều 2: Niên kim nhân thọ trọn đời trả đầu kỳ

Niên kim nhân thọ trọn đời trả đầu kỳ (1 đơn vị mỗi năm, đầu năm, khi người
được bảo hiểm còn sống), tuổi $x$, được xác định theo:

$$\\ddot{a}_x = \\sum_{k=0}^{\\infty} v^k \\cdot {}_kp_x$$

trong đó:

- $v = \\dfrac{1}{1+i}$ là hệ số chiết khấu ứng với lãi suất kỹ thuật $i$;
- ${}_kp_x = \\dfrac{l_{x+k}}{l_x}$ là xác suất một người tuổi $x$ còn sống sau $k$ năm;
- $\\ddot{a}_x$ là giá trị hiện tại của niên kim (1 đơn vị/năm, trả đầu kỳ) trọn đời.

## Điều 3: Liên hệ giữa bảo hiểm trọn đời và niên kim

Giá trị hiện tại của bảo hiểm tử kỳ trọn đời $A_x$ và niên kim nhân thọ trọn
đời $\\ddot{a}_x$ liên hệ với nhau qua hệ số chiết khấu:

$$A_x = 1 - d \\cdot \\ddot{a}_x, \\qquad d = 1 - v$$

trong đó $d$ là suất chiết khấu (discount rate) tương ứng với lãi suất kỹ
thuật $i$.
"""

PROCEDURE_CLAIMS = """\
# Quy trình Giải quyết Quyền lợi Bảo hiểm (bản giả định)

## Điều 1: Hồ sơ yêu cầu giải quyết quyền lợi

Hồ sơ bao gồm:

1. Giấy yêu cầu giải quyết quyền lợi bảo hiểm theo mẫu.
2. Bản sao Giấy chứng nhận bảo hiểm.
3. Giấy tờ chứng minh sự kiện bảo hiểm.

## Điều 2: Thời hạn giải quyết

Công ty giải quyết trong vòng 30 ngày kể từ ngày nhận đủ hồ sơ hợp lệ.

## Điều 3: Bảng thời hạn xử lý theo loại quyền lợi

| Loại quyền lợi | Thời hạn thẩm định | Bộ phận phụ trách |
| --- | --- | --- |
| Quyền lợi tử vong | 30 ngày | Ban Bồi thường |
| Quyền lợi đáo hạn | 15 ngày | Ban Nghiệp vụ |
| Tạm ứng giá trị hoàn lại | 10 ngày | Ban Dịch vụ khách hàng |
"""

# Universal-life trap doc: interest-by-year table sits next to a death-benefit
# clause so retrieval/generation cannot confuse lãi suất cam kết with claim %.
POLICY_UL_AN_PHU = """\
# Quy tắc, Điều khoản Sản phẩm Bảo hiểm liên kết chung "An Phú Liên Kết"

Mã sản phẩm: APLK-2025 (sản phẩm giả định phục vụ kiểm thử).

## Chương I: Quyền lợi bảo hiểm

### Điều 1: Quyền lợi tử vong do tai nạn

Nếu Người được bảo hiểm tử vong do tai nạn giao thông trong Thời hạn hợp đồng
và Hợp đồng đang có hiệu lực, Công ty chi trả **100% Số tiền bảo hiểm** cộng
Giá trị tài khoản hợp đồng tại thời điểm xảy ra sự kiện bảo hiểm. Đây là số tiền
chi trả quyền lợi, không phải tỷ lệ lãi suất.

### Điều 2: Loại trừ trách nhiệm bảo hiểm

Công ty không chi trả quyền lợi tử vong do tai nạn nếu sự kiện phát sinh từ
hoạt động thể thao nguy hiểm (trượt tuyết, lặn biển có bình khí) hoặc từ hành vi
vi phạm pháp luật của Người được bảo hiểm.

## Chương II: Phí và lãi suất quỹ liên kết chung

### Điều 3: Phí ban đầu

Phí ban đầu được khấu trừ theo tỷ lệ trên phí bảo hiểm định kỳ đóng trong từng
năm hợp đồng, theo biểu phí đính kèm.

### Điều 4: Lãi suất cam kết tối thiểu

Lãi suất cam kết tối thiểu áp dụng cho Giá trị tài khoản hợp đồng theo năm hợp
đồng như sau (đây là lãi suất đầu tư cam kết, **không phải** tỷ lệ bồi thường
khi tử vong):

| Năm hợp đồng | Lãi suất cam kết tối thiểu (%) |
| --- | --- |
| Năm 1 | 2.5 |
| Năm 2 | 2.0 |
| Năm 3 | 1.5 |
| Năm 4 đến năm 10 | 1.0 |
| Năm 11 đến năm 15 | 0.5 |
| Từ năm 16 trở đi | 0.25 |
"""


DOCUMENTS: dict[str, str] = {
    "quy_tac_tu_ky_an_tam.md": POLICY_TERM_LIFE,
    "huong_dan_du_phong_toan_hoc.md": DOC_RESERVES,
    "cong_thuc_nien_kim_bang_ty_le_tu_vong.md": ANNUITY_MORTALITY,
    "quy_trinh_giai_quyet_quyen_loi.md": PROCEDURE_CLAIMS,
    "quy_tac_lien_ket_chung_an_phu.md": POLICY_UL_AN_PHU,
}

# --------------------------------------------------------------------------- #
# Claims-payout XLSX (invented data; matches golden_set.jsonl q22-q25)
# --------------------------------------------------------------------------- #

XLSX_FILENAME = "danh_sach_chi_tra_quyen_loi_q1_2025.xlsx"

_CLAIMS_HEADER = [
    "Mã hồ sơ",
    "Sản phẩm",
    "Loại quyền lợi",
    "Ngày nộp hồ sơ",
    "Số ngày xử lý",
    "Số tiền chi trả (VND)",
    "Trạng thái",
]
_CLAIMS_ROWS: list[list[object]] = [
    [
        "HS-2025-0001",
        "An Tâm Bảo Vệ",
        "Quyền lợi tử vong",
        date(2025, 1, 14),
        22,
        500_000_000,
        "Đã chi trả",
    ],
    [
        "HS-2025-0002",
        "An Tâm Bảo Vệ",
        "Quyền lợi đáo hạn",
        date(2025, 1, 20),
        12,
        150_000_000,
        "Đã chi trả",
    ],
    [
        "HS-2025-0003",
        "An Khang Hưu Trí",
        "Tạm ứng giá trị hoàn lại",
        date(2025, 2, 3),
        8,
        40_000_000,
        "Đã chi trả",
    ],
    [
        "HS-2025-0004",
        "An Tâm Bảo Vệ",
        "Quyền lợi tử vong",
        date(2025, 2, 11),
        28,
        750_000_000,
        "Đã chi trả",
    ],
    [
        "HS-2025-0005",
        "An Khang Hưu Trí",
        "Quyền lợi đáo hạn",
        date(2025, 2, 25),
        14,
        200_000_000,
        "Đã chi trả",
    ],
    [
        "HS-2025-0006",
        "An Tâm Bảo Vệ",
        "Quyền lợi tử vong",
        date(2025, 3, 7),
        35,
        0,
        "Từ chối",
    ],
    [
        "HS-2025-0007",
        "An Tâm Bảo Vệ",
        "Quyền lợi đáo hạn",
        date(2025, 3, 18),
        9,
        120_000_000,
        "Đã chi trả",
    ],
    [
        "HS-2025-0008",
        "An Khang Hưu Trí",
        "Tạm ứng giá trị hoàn lại",
        date(2025, 3, 28),
        5,
        30_000_000,
        "Đang xử lý",
    ],
]
_SUMMARY_ROWS: list[list[object]] = [
    ["Chỉ tiêu", "Giá trị"],
    ["Tổng số hồ sơ Q1/2025", 8],
    ["Số hồ sơ đã chi trả", 6],
    ["Số hồ sơ từ chối", 1],
    ["Số hồ sơ đang xử lý", 1],
    ["Tổng số tiền đã chi trả (VND)", 1_760_000_000],
    ["Số ngày xử lý trung bình của hồ sơ đã chi trả", 15.5],
]


def write_claims_xlsx(path: Path) -> None:
    """Write the fake claims-payout workbook (two sheets: detail + summary)."""
    from openpyxl import Workbook  # dev-time dependency (requirements-embed.txt)

    wb = Workbook()
    # Read back by parse_xlsx as doc_title (filenames lose VN diacritics).
    wb.properties.title = "Danh sách chi trả quyền lợi bảo hiểm Quý 1/2025"
    detail = wb.active
    detail.title = "Chi trả Q1-2025"
    detail.append(_CLAIMS_HEADER)
    for row in _CLAIMS_ROWS:
        detail.append(row)
    summary = wb.create_sheet("Tổng hợp")
    for row in _SUMMARY_ROWS:
        summary.append(row)
    wb.save(path)


# --------------------------------------------------------------------------- #
# Underwriting-guide PDF (invented; matches golden_set.jsonl q26-q27)
# --------------------------------------------------------------------------- #

PDF_FILENAME = "huong_dan_tham_dinh_so_bo.pdf"

_PDF_TITLE = "Hướng dẫn Thẩm định Sơ bộ Hợp đồng (bản giả định)"
# (heading, body) pairs; rendered with distinct font sizes so Docling's layout
# model classifies the headings and the sectionizer builds Điều paths.
_PDF_SECTIONS: list[tuple[str, str]] = [
    (
        "Điều 1: Mục đích",
        "Tài liệu này hướng dẫn quy trình thẩm định sơ bộ hồ sơ yêu cầu bảo hiểm "
        "trước khi phát hành hợp đồng. Toàn bộ nội dung là giả định phục vụ kiểm thử.",
    ),
    (
        "Điều 2: Ngưỡng khám y tế",
        "Khách hàng trên 50 tuổi hoặc có Số tiền bảo hiểm trên 2 tỷ đồng phải "
        "thực hiện khám y tế trước khi phát hành hợp đồng. Các trường hợp còn lại "
        "được thẩm định trên hồ sơ kê khai sức khỏe.",
    ),
    (
        "Điều 3: Thời hạn xử lý",
        "Hồ sơ thẩm định sơ bộ được xử lý trong vòng 5 ngày làm việc kể từ ngày "
        "nhận đủ giấy tờ hợp lệ. Trường hợp cần khám y tế, thời hạn tính từ ngày "
        "nhận kết quả khám.",
    ),
]

# Vietnamese text needs a Unicode TTF; reportlab's built-in Helvetica is Latin-1.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Debian/Ubuntu
]


def write_underwriting_pdf(path: Path) -> bool:
    """Write the fake underwriting-guide PDF (text layer, VN diacritics).

    Dev-time only; returns False (with a hint) when reportlab or a suitable
    Unicode font is unavailable instead of failing the whole corpus.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen.canvas import Canvas
    except ImportError:
        print(
            f"WARN: reportlab not installed; skipped {path.name} (pip install reportlab)"
        )
        return False

    font_file = next((f for f in _FONT_CANDIDATES if Path(f).exists()), None)
    if font_file is None:
        print(f"WARN: no Unicode TTF found; skipped {path.name}")
        return False
    pdfmetrics.registerFont(TTFont("VNFont", font_file))

    canvas = Canvas(str(path), pagesize=A4)
    _, height = A4
    y = height - 70

    def line(text: str, size: int, gap: int) -> None:
        nonlocal y
        canvas.setFont("VNFont", size)
        canvas.drawString(60, y, unicodedata.normalize("NFC", text))
        y -= gap

    line(_PDF_TITLE, 16, 34)
    for heading, body in _PDF_SECTIONS:
        line(heading, 13, 24)
        # Naive wrap: the body strings are short enough for ~90-char lines.
        words, cur = body.split(), ""
        for word in words:
            if len(cur) + len(word) + 1 > 90:
                line(cur, 11, 16)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        if cur:
            line(cur, 11, 26)
    canvas.showPage()
    canvas.save()
    return True


def main() -> None:
    """Write the synthetic corpus (NFC-normalized) to data/synthetic/."""
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    n_written = 0
    for filename, content in DOCUMENTS.items():
        # NFC-normalize at generation so fixtures match ingestion expectations.
        normalized = unicodedata.normalize("NFC", content)
        path = SYNTHETIC_DIR / filename
        path.write_text(normalized, encoding="utf-8")
        print(f"wrote {path.relative_to(SYNTHETIC_DIR.parent.parent)}")
        n_written += 1
    xlsx_path = SYNTHETIC_DIR / XLSX_FILENAME
    write_claims_xlsx(xlsx_path)
    print(f"wrote {xlsx_path.relative_to(SYNTHETIC_DIR.parent.parent)}")
    n_written += 1
    pdf_path = SYNTHETIC_DIR / PDF_FILENAME
    if write_underwriting_pdf(pdf_path):
        print(f"wrote {pdf_path.relative_to(SYNTHETIC_DIR.parent.parent)}")
        n_written += 1
    print(f"\n{n_written} synthetic documents written to {SYNTHETIC_DIR}")


if __name__ == "__main__":
    main()
