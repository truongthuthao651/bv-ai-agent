"""Generate a small synthetic Vietnamese insurance corpus for dev/testing.

Writes fake documents to ``data/synthetic/`` ONLY. Everything here is invented —
company names, product names, policy numbers, and amounts are all fictional; the
actuarial formulas are textbook-standard (life contingencies) and therefore not
confidential. See the insurance-rag-pipeline skill, section 7, and the security
rules in CLAUDE.md.

Phase 2 (easy path) emits Markdown — the canonical format the pipeline already
speaks. A DOCX (with real OMML equations, via pandoc) and scanned/figure samples
are added in the hard-parser increment.

Run:
    python scripts/make_synthetic_data.py
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

# Repo-relative output dir (this script runs on the host, not in the container,
# so we don't use the container-absolute settings paths here).
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


DOCUMENTS: dict[str, str] = {
    "quy_tac_tu_ky_an_tam.md": POLICY_TERM_LIFE,
    "huong_dan_du_phong_toan_hoc.md": DOC_RESERVES,
    "quy_trinh_giai_quyet_quyen_loi.md": PROCEDURE_CLAIMS,
}


def main() -> None:
    """Write the synthetic corpus (NFC-normalized) to data/synthetic/."""
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in DOCUMENTS.items():
        # NFC-normalize at generation so fixtures match ingestion expectations.
        normalized = unicodedata.normalize("NFC", content)
        path = SYNTHETIC_DIR / filename
        path.write_text(normalized, encoding="utf-8")
        print(f"wrote {path.relative_to(SYNTHETIC_DIR.parent.parent)}")
    print(f"\n{len(DOCUMENTS)} synthetic documents written to {SYNTHETIC_DIR}")


if __name__ == "__main__":
    main()
