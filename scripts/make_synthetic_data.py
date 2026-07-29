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

### Điều 2b: Loại trừ bổ sung theo kết quả thẩm định

Ngoài các trường hợp loại trừ nêu tại Điều 2, Công ty có thể áp dụng các điểm
loại trừ bổ sung đối với từng Hợp đồng cụ thể căn cứ kết quả thẩm định rủi ro
tại thời điểm phát hành, khi Người được bảo hiểm có tình trạng sức khỏe dưới
chuẩn hoặc có yếu tố rủi ro nghề nghiệp dưới chuẩn. Nội dung và phạm vi của
từng điểm loại trừ bổ sung được ghi rõ trong Giấy chứng nhận bảo hiểm hoặc Phụ
lục hợp đồng của Hợp đồng đó và chỉ có hiệu lực đối với Hợp đồng đó.

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


# Full-length policy booklet. The other Markdown documents are deliberately
# terse, which makes every chunk far smaller than CHUNK_MAX_TOKENS and leaves
# parent-child chunking with nothing to split (scripts/chunk_stats.py). This one
# is written at the density of a real Vietnamese policy booklet — articles of
# 500-800 tokens with several khoản each — so chunking, retrieval precision and
# rerank cost are exercised the way they will be on company documents.
#
# It is also built around the failure mode parent-child chunking exists to fix:
# in Điều 9 the qualifying condition (24 tháng) sits several paragraphs away
# from the formula that answers "how is it calculated", so a narrow child match
# is only correct once the parent window is handed to generation.
POLICY_WHOLE_LIFE = """\
# Quy tắc, Điều khoản Sản phẩm Bảo hiểm Nhân thọ Trọn đời "An Bình Trọn Đời"

Mã sản phẩm: ABTD-2025 (sản phẩm giả định phục vụ kiểm thử).

## Chương I: Quy định chung

### Điều 1: Giải thích từ ngữ

Trong bản Quy tắc và Điều khoản này, các từ ngữ dưới đây được hiểu thống nhất
như sau:

1. **Hợp đồng bảo hiểm** là thỏa thuận bằng văn bản giữa Bên mua bảo hiểm và
Công ty, bao gồm Giấy yêu cầu bảo hiểm, Giấy chứng nhận bảo hiểm, bản Quy tắc
và Điều khoản này, các phụ lục kèm theo và mọi thỏa thuận sửa đổi, bổ sung được
Công ty chấp thuận bằng văn bản.

2. **Bên mua bảo hiểm** là cá nhân từ đủ 18 tuổi trở lên có năng lực hành vi
dân sự đầy đủ, hoặc tổ chức được thành lập hợp pháp tại Việt Nam, kê khai Giấy
yêu cầu bảo hiểm và có nghĩa vụ đóng phí bảo hiểm theo Hợp đồng.

3. **Người được bảo hiểm** là cá nhân được Công ty chấp nhận bảo hiểm và có tên
trên Giấy chứng nhận bảo hiểm. Mỗi Hợp đồng chỉ có một Người được bảo hiểm.

4. **Người thụ hưởng** là cá nhân hoặc tổ chức được Bên mua bảo hiểm chỉ định
bằng văn bản để nhận quyền lợi bảo hiểm. Bên mua bảo hiểm có quyền thay đổi
Người thụ hưởng và việc thay đổi chỉ có hiệu lực khi được Công ty xác nhận.

5. **Số tiền bảo hiểm** là số tiền do Bên mua bảo hiểm và Công ty thỏa thuận,
được ghi trên Giấy chứng nhận bảo hiểm, làm căn cứ xác định quyền lợi bảo hiểm.

6. **Năm hợp đồng** là khoảng thời gian mười hai (12) tháng liên tục tính từ
Ngày hiệu lực hợp đồng hoặc từ Ngày kỷ niệm hợp đồng của các năm tiếp theo.

7. **Ngày kỷ niệm hợp đồng** là ngày tương ứng với Ngày hiệu lực hợp đồng của
mỗi năm hợp đồng tiếp theo.

8. **Tuổi bảo hiểm** là tuổi của Người được bảo hiểm tính theo lần sinh nhật
gần nhất so với Ngày hiệu lực hợp đồng.

9. **Giá trị hoàn lại** là số tiền Công ty chi trả cho Bên mua bảo hiểm khi Hợp
đồng chấm dứt trước thời hạn theo yêu cầu của Bên mua bảo hiểm, được xác định
theo quy định tại Điều 9 của bản Quy tắc này.

10. **Sự kiện bảo hiểm** là sự kiện khách quan do các bên thỏa thuận mà khi sự
kiện đó xảy ra thì Công ty có nghĩa vụ chi trả quyền lợi bảo hiểm.

11. **Phí bảo hiểm** là khoản tiền Bên mua bảo hiểm có nghĩa vụ đóng cho Công ty
theo định kỳ và mức đã thỏa thuận, được ghi trên Giấy chứng nhận bảo hiểm, để
Công ty thực hiện nghĩa vụ chi trả quyền lợi bảo hiểm theo Hợp đồng.

12. **Ngày hiệu lực hợp đồng** là ngày Hợp đồng bắt đầu phát sinh hiệu lực, được
ghi trên Giấy chứng nhận bảo hiểm, và là mốc để tính Năm hợp đồng, Tuổi bảo hiểm
cũng như các thời hạn quy định trong bản Quy tắc này.

13. **Thời gian gia hạn đóng phí** là khoảng thời gian Công ty cho phép Bên mua
bảo hiểm đóng khoản phí bảo hiểm đến hạn mà Hợp đồng vẫn giữ nguyên hiệu lực,
được quy định tại Điều 8 của bản Quy tắc này.

14. **Giấy chứng nhận bảo hiểm** là văn bản do Công ty phát hành xác nhận việc
giao kết Hợp đồng, ghi nhận Số tiền bảo hiểm, phí bảo hiểm, định kỳ đóng phí,
Ngày hiệu lực hợp đồng và các thông tin cơ bản khác của Hợp đồng.

15. **Khoản nợ của Hợp đồng** là tổng số tiền Bên mua bảo hiểm còn nợ Công ty
tại một thời điểm, bao gồm khoản tạm ứng từ Giá trị hoàn lại, khoản phí bảo hiểm
được tạm ứng tự động và lãi phát sinh của các khoản đó.

### Điều 2: Đối tượng và điều kiện tham gia bảo hiểm

Người được bảo hiểm phải có Tuổi bảo hiểm từ đủ ba mươi (30) ngày tuổi đến sáu
mươi lăm (65) tuổi tại Ngày hiệu lực hợp đồng, đang cư trú hợp pháp tại Việt
Nam và được Công ty chấp nhận bảo hiểm sau khi thẩm định.

Số tiền bảo hiểm tối thiểu của một Hợp đồng là một trăm triệu (100.000.000)
đồng. Số tiền bảo hiểm tối đa phụ thuộc vào kết quả thẩm định và thu nhập kê
khai của Bên mua bảo hiểm.

Người được bảo hiểm có Tuổi bảo hiểm trên năm mươi (50) tuổi, hoặc tham gia với
Số tiền bảo hiểm trên hai (2) tỷ đồng, phải thực hiện kiểm tra y tế theo yêu
cầu của Công ty trước khi Hợp đồng được phát hành.

Bên mua bảo hiểm có nghĩa vụ kê khai đầy đủ, trung thực mọi thông tin được yêu
cầu trong Giấy yêu cầu bảo hiểm. Việc kê khai không trung thực nhằm mục đích
được Công ty chấp nhận bảo hiểm là căn cứ để Công ty từ chối chi trả quyền lợi
bảo hiểm và chấm dứt Hợp đồng theo quy định của pháp luật.

### Điều 3: Hiệu lực hợp đồng và thời gian cân nhắc

Hợp đồng có hiệu lực kể từ Ngày hiệu lực hợp đồng ghi trên Giấy chứng nhận bảo
hiểm, với điều kiện Bên mua bảo hiểm đã đóng đủ khoản phí bảo hiểm đầu tiên và
Người được bảo hiểm còn sống tại thời điểm phát hành Hợp đồng.

Trong thời hạn hai mươi mốt (21) ngày kể từ ngày nhận được Hợp đồng, Bên mua
bảo hiểm có quyền từ chối tiếp tục tham gia bảo hiểm. Trong trường hợp này Công
ty hoàn lại khoản phí bảo hiểm đã đóng sau khi trừ chi phí kiểm tra y tế thực tế
đã phát sinh, và Hợp đồng được coi như chưa từng có hiệu lực.

Hợp đồng chấm dứt hiệu lực trong các trường hợp: Người được bảo hiểm tử vong;
Bên mua bảo hiểm yêu cầu chấm dứt Hợp đồng và nhận Giá trị hoàn lại; Hợp đồng
mất hiệu lực do không đóng phí sau khi hết Thời gian gia hạn đóng phí và không
được khôi phục; hoặc các trường hợp khác theo quy định của pháp luật.

## Chương II: Quyền lợi bảo hiểm

### Điều 4: Quyền lợi bảo hiểm tử vong

Nếu Người được bảo hiểm tử vong trong khi Hợp đồng đang có hiệu lực, Công ty chi
trả cho Người thụ hưởng một trăm phần trăm (100%) Số tiền bảo hiểm, cộng với
khoản lãi chia tích lũy (nếu có), sau khi trừ các khoản nợ phát sinh từ Hợp
đồng bao gồm khoản tạm ứng từ Giá trị hoàn lại và lãi của khoản tạm ứng đó.

Sản phẩm An Bình Trọn Đời bảo vệ trọn đời, nghĩa là quyền lợi tử vong được duy
trì đến khi Người được bảo hiểm tử vong, không giới hạn ở một thời hạn hợp đồng
nhất định, với điều kiện Hợp đồng đang có hiệu lực tại thời điểm xảy ra sự kiện
bảo hiểm.

Trường hợp Người được bảo hiểm tử vong do tự tử trong vòng hai mươi bốn (24)
tháng kể từ Ngày hiệu lực hợp đồng hoặc kể từ ngày Hợp đồng được khôi phục hiệu
lực gần nhất, Công ty không chi trả quyền lợi tử vong mà chỉ hoàn lại Giá trị
hoàn lại của Hợp đồng tại thời điểm đó.

Hồ sơ yêu cầu chi trả quyền lợi tử vong phải được gửi đến Công ty trong vòng một
(1) năm kể từ ngày xảy ra sự kiện bảo hiểm, trừ trường hợp có lý do khách quan
được Công ty chấp thuận.

Hồ sơ yêu cầu chi trả quyền lợi tử vong bao gồm: Giấy yêu cầu giải quyết quyền
lợi bảo hiểm theo mẫu của Công ty; bản sao Giấy chứng nhận bảo hiểm; bản sao
giấy chứng tử của Người được bảo hiểm; bản sao giấy tờ tùy thân của Người thụ
hưởng; và các giấy tờ chứng minh nguyên nhân tử vong do cơ quan có thẩm quyền
cấp.

Công ty chi trả quyền lợi tử vong trong vòng ba mươi (30) ngày kể từ ngày nhận
đủ hồ sơ hợp lệ. Trường hợp cần xác minh thêm về nguyên nhân tử vong hoặc về
tính trung thực của thông tin kê khai, thời hạn xác minh không quá chín mươi
(90) ngày và Công ty phải thông báo bằng văn bản cho Người thụ hưởng về lý do
cũng như tiến độ xác minh.

Trường hợp Người thụ hưởng không được chỉ định hoặc Người thụ hưởng đã chết
trước Người được bảo hiểm mà không có chỉ định thay thế, quyền lợi bảo hiểm được
chi trả cho những người thừa kế hợp pháp của Người được bảo hiểm theo quy định
của pháp luật về thừa kế.

### Điều 5: Quyền lợi thương tật toàn bộ vĩnh viễn

Thương tật toàn bộ vĩnh viễn là tình trạng Người được bảo hiểm bị mất hoàn toàn
và không thể phục hồi khả năng lao động, hoặc mất hoàn toàn chức năng của hai
chi, hai mắt, hoặc một chi và một mắt, kéo dài liên tục ít nhất một trăm tám
mươi (180) ngày kể từ ngày xảy ra sự kiện và được cơ sở y tế có thẩm quyền xác
nhận.

Nếu Người được bảo hiểm bị Thương tật toàn bộ vĩnh viễn trước Ngày kỷ niệm hợp
đồng mà tại đó Tuổi bảo hiểm đạt bảy mươi (70) tuổi, và trong khi Hợp đồng đang
có hiệu lực, Công ty chi trả một trăm phần trăm (100%) Số tiền bảo hiểm.

Quyền lợi Thương tật toàn bộ vĩnh viễn và quyền lợi tử vong không được chi trả
đồng thời cho cùng một Hợp đồng. Sau khi Công ty đã chi trả quyền lợi Thương tật
toàn bộ vĩnh viễn, Hợp đồng chấm dứt hiệu lực và Công ty không có nghĩa vụ chi
trả bất kỳ quyền lợi nào khác.

### Điều 6: Điều khoản loại trừ trách nhiệm bảo hiểm

Công ty không chi trả quyền lợi bảo hiểm nếu sự kiện bảo hiểm xảy ra thuộc một
trong các trường hợp sau đây:

1. Người được bảo hiểm tự tử trong vòng hai mươi bốn (24) tháng kể từ Ngày hiệu
lực hợp đồng hoặc kể từ ngày khôi phục hiệu lực gần nhất.

2. Người được bảo hiểm bị thương tật hoặc tử vong do hành vi cố ý của Bên mua
bảo hiểm hoặc của Người thụ hưởng.

3. Người được bảo hiểm tham gia đánh nhau, trừ trường hợp tự vệ chính đáng được
cơ quan có thẩm quyền xác nhận.

4. Sự kiện bảo hiểm phát sinh trong khi Người được bảo hiểm đang thực hiện hành
vi vi phạm pháp luật hình sự hoặc đang chấp hành hình phạt tù.

5. Sự kiện bảo hiểm phát sinh do chiến tranh, nội chiến, bạo loạn, khủng bố có
tổ chức, hoặc do nhiễm phóng xạ từ nhiên liệu hạt nhân.

6. Người được bảo hiểm tham gia chuyến bay không phải với tư cách hành khách
trên chuyến bay thương mại của hãng hàng không được cấp phép.

7. Người được bảo hiểm sử dụng ma túy hoặc chất gây nghiện trái quy định của
pháp luật, hoặc điều khiển phương tiện giao thông khi nồng độ cồn trong máu, khí
thở vượt quá mức cho phép theo quy định của pháp luật Việt Nam.

8. Người được bảo hiểm tham gia thi đấu hoặc luyện tập chuyên nghiệp các môn thể
thao đối kháng, đua xe, nhảy dù, leo núi có sử dụng dây bảo hộ chuyên dụng, hoặc
lặn biển có bình khí.

Trường hợp sự kiện bảo hiểm thuộc một trong các trường hợp loại trừ nêu trên,
Công ty hoàn lại Giá trị hoàn lại của Hợp đồng tại thời điểm xảy ra sự kiện (nếu
Hợp đồng đã có Giá trị hoàn lại) và Hợp đồng chấm dứt hiệu lực.

Các trường hợp loại trừ nêu trên chỉ được áp dụng khi sự kiện bảo hiểm thực tế
thỏa mãn đúng điều kiện mô tả tại khoản tương ứng. Một tai nạn thông thường
trong sinh hoạt hoặc khi tham gia giao thông đúng quy định của pháp luật không
thuộc bất kỳ trường hợp loại trừ nào của Điều này. Ngoài các trường hợp được
liệt kê tại Điều này, Công ty không viện dẫn bất kỳ lý do loại trừ nào khác để
từ chối chi trả quyền lợi bảo hiểm.

## Chương III: Phí bảo hiểm và giá trị hợp đồng

### Điều 7: Phí bảo hiểm và định kỳ đóng phí

Phí bảo hiểm được xác định căn cứ vào Tuổi bảo hiểm, giới tính, Số tiền bảo
hiểm, định kỳ đóng phí và kết quả thẩm định của Công ty tại thời điểm phát hành
Hợp đồng. Phí bảo hiểm không thay đổi trong suốt thời gian đóng phí, trừ trường
hợp Bên mua bảo hiểm yêu cầu điều chỉnh Số tiền bảo hiểm và được Công ty chấp
thuận.

Bên mua bảo hiểm lựa chọn đóng phí theo định kỳ năm, nửa năm, quý hoặc tháng.
Định kỳ đóng phí có thể được thay đổi vào Ngày kỷ niệm hợp đồng trên cơ sở yêu
cầu bằng văn bản của Bên mua bảo hiểm và được Công ty chấp thuận.

Thời gian đóng phí của sản phẩm An Bình Trọn Đời kéo dài đến Ngày kỷ niệm hợp
đồng mà tại đó Tuổi bảo hiểm của Người được bảo hiểm đạt chín mươi chín (99)
tuổi. Bên mua bảo hiểm có thể lựa chọn thời gian đóng phí rút gọn mười lăm (15)
năm hoặc hai mươi (20) năm theo biểu phí tương ứng.

Phí bảo hiểm được coi là đã đóng khi Công ty hoặc đại lý được Công ty ủy quyền
thực tế nhận được tiền và cấp biên lai hợp lệ. Trường hợp đóng phí bằng chuyển
khoản, thời điểm đóng phí là thời điểm tiền được ghi có vào tài khoản của Công
ty. Công ty không chịu trách nhiệm đối với khoản tiền được giao cho cá nhân
không có ủy quyền hợp lệ.

Bên mua bảo hiểm có quyền yêu cầu giảm Số tiền bảo hiểm vào bất kỳ Ngày kỷ niệm
hợp đồng nào, với điều kiện Số tiền bảo hiểm sau khi giảm không thấp hơn mức tối
thiểu quy định tại Điều 2. Việc tăng Số tiền bảo hiểm phải được thẩm định lại và
chỉ áp dụng cho các sự kiện bảo hiểm xảy ra sau ngày Công ty chấp thuận bằng văn
bản.

### Điều 8: Thời gian gia hạn đóng phí và khôi phục hiệu lực

Thời gian gia hạn đóng phí là sáu mươi (60) ngày kể từ ngày đến hạn đóng phí.
Trong Thời gian gia hạn đóng phí, Hợp đồng vẫn có hiệu lực và Công ty vẫn chi
trả quyền lợi bảo hiểm nếu sự kiện bảo hiểm xảy ra, sau khi trừ khoản phí bảo
hiểm còn nợ.

Nếu hết Thời gian gia hạn đóng phí mà Bên mua bảo hiểm vẫn chưa đóng phí, Hợp
đồng mất hiệu lực kể từ ngày đến hạn đóng phí gần nhất. Trường hợp Hợp đồng đã
có Giá trị hoàn lại, Công ty tự động áp dụng điều khoản tạm ứng phí tự động để
duy trì hiệu lực Hợp đồng cho đến khi Giá trị hoàn lại không còn đủ để đóng phí.

Trong vòng hai (2) năm kể từ ngày Hợp đồng mất hiệu lực, Bên mua bảo hiểm có
quyền yêu cầu khôi phục hiệu lực Hợp đồng với điều kiện nộp đủ phí bảo hiểm còn
nợ cùng lãi chậm đóng, cung cấp bằng chứng về khả năng được bảo hiểm của Người
được bảo hiểm và được Công ty chấp thuận. Quy định loại trừ tự tử hai mươi bốn
(24) tháng được tính lại từ ngày khôi phục hiệu lực.

### Điều 9: Giá trị hoàn lại

Hợp đồng chỉ bắt đầu có Giá trị hoàn lại sau khi Bên mua bảo hiểm đã đóng đủ phí
bảo hiểm của hai mươi bốn (24) tháng đầu tiên và Hợp đồng đang có hiệu lực. Hợp
đồng chấm dứt trước thời điểm này không phát sinh Giá trị hoàn lại và Công ty
không hoàn lại khoản phí bảo hiểm đã đóng.

Giá trị hoàn lại tại thời điểm kết thúc năm hợp đồng thứ $t$ được xác định theo
công thức:

$$GTHL_t = S \\cdot r_t - L_t$$

trong đó:

- $GTHL_t$ là Giá trị hoàn lại tại thời điểm kết thúc năm hợp đồng thứ $t$;
- $S$ là Số tiền bảo hiểm ghi trên Giấy chứng nhận bảo hiểm;
- $r_t$ là tỷ lệ giá trị hoàn lại của năm hợp đồng thứ $t$ theo bảng dưới đây;
- $L_t$ là tổng các khoản nợ của Hợp đồng tại thời điểm đó, gồm khoản tạm ứng từ
Giá trị hoàn lại, phí bảo hiểm được tạm ứng tự động và lãi phát sinh.

Tỷ lệ giá trị hoàn lại $r_t$ trên Số tiền bảo hiểm theo năm hợp đồng (đây là tỷ
lệ dùng để tính giá trị hoàn lại khi chấm dứt hợp đồng trước hạn, **không phải**
tỷ lệ chi trả quyền lợi tử vong và **không phải** lãi suất đầu tư):

| Năm hợp đồng | Tỷ lệ giá trị hoàn lại (%) |
| --- | --- |
| Năm 1 | 0 |
| Năm 2 | 0 |
| Năm 3 | 8 |
| Năm 4 | 14 |
| Năm 5 | 20 |
| Năm 10 | 38 |
| Năm 15 | 52 |
| Năm 20 | 65 |

Đối với các năm hợp đồng không được liệt kê trong bảng nêu trên, tỷ lệ giá trị
hoàn lại được xác định bằng phương pháp nội suy tuyến tính giữa hai năm hợp đồng
liền kề có trong bảng. Từ năm hợp đồng thứ hai mươi mốt (21) trở đi, tỷ lệ giá
trị hoàn lại tăng thêm một phẩy năm phần trăm (1,5%) cho mỗi năm hợp đồng và
không vượt quá một trăm phần trăm (100%) Số tiền bảo hiểm.

Công ty chi trả Giá trị hoàn lại trong vòng ba mươi (30) ngày kể từ ngày nhận
được yêu cầu hợp lệ bằng văn bản của Bên mua bảo hiểm. Kể từ thời điểm Công ty
chi trả Giá trị hoàn lại, Hợp đồng chấm dứt hiệu lực và mọi quyền lợi bảo hiểm
theo Hợp đồng cũng chấm dứt.

Thay cho việc nhận Giá trị hoàn lại bằng tiền, Bên mua bảo hiểm có quyền lựa
chọn chuyển Hợp đồng sang trạng thái đóng phí đầy đủ với Số tiền bảo hiểm giảm,
được xác định trên cơ sở Giá trị hoàn lại tại thời điểm chuyển đổi. Khi đó Bên
mua bảo hiểm không phải đóng thêm phí bảo hiểm và quyền lợi tử vong tiếp tục
được duy trì theo Số tiền bảo hiểm giảm cho đến khi Người được bảo hiểm tử vong.

### Điều 10: Tạm ứng từ giá trị hoàn lại

Khi Hợp đồng đã có Giá trị hoàn lại, Bên mua bảo hiểm có quyền yêu cầu tạm ứng
một phần Giá trị hoàn lại với hạn mức tối đa bằng tám mươi phần trăm (80%) Giá
trị hoàn lại tại thời điểm yêu cầu, sau khi trừ các khoản nợ hiện có của Hợp
đồng.

Khoản tạm ứng chịu lãi suất do Công ty công bố tại từng thời kỳ và được cộng dồn
vào khoản nợ của Hợp đồng. Bên mua bảo hiểm có thể hoàn trả khoản tạm ứng và lãi
vào bất kỳ thời điểm nào trong khi Hợp đồng đang có hiệu lực.

Nếu tổng khoản nợ của Hợp đồng vượt quá Giá trị hoàn lại, Hợp đồng mất hiệu lực
sau khi Công ty gửi thông báo bằng văn bản cho Bên mua bảo hiểm và Bên mua bảo
hiểm không hoàn trả phần vượt trong vòng ba mươi (30) ngày kể từ ngày thông báo.
"""


# Long-form endowment booklet. Deliberately exclusion-HEAVY (a whole chapter,
# four articles) with benefit clauses that use different vocabulary, so a
# coverage question ("bị X có được chi trả không?") has to compete with
# exclusions for the top-k — the retrieval shape that produced the real-doc
# denial the short synthetic docs could not reproduce.
POLICY_ENDOWMENT_AN_VUI = r"""# Quy tắc, Điều khoản Sản phẩm Bảo hiểm Hỗn hợp "An Vui Toàn Diện"

Mã sản phẩm: AVTD-2025 (sản phẩm giả định phục vụ kiểm thử, không có thật).

## Chương I: Định nghĩa và phạm vi áp dụng

### Điều 1: Giải thích từ ngữ

Trong Quy tắc, Điều khoản này, các từ ngữ dưới đây được hiểu như sau:

**Người được bảo hiểm** là cá nhân được chấp nhận bảo hiểm theo Hợp đồng này và
có tên trên Giấy chứng nhận bảo hiểm.

**Sự kiện bảo hiểm** là sự kiện khách quan do các bên thỏa thuận tại Quy tắc,
Điều khoản này mà khi xảy ra thì Công ty phải chi trả quyền lợi bảo hiểm.

**Tai nạn** là sự kiện bất ngờ, không lường trước, xảy ra do một lực bên ngoài
tác động lên cơ thể Người được bảo hiểm, độc lập với mọi nguyên nhân khác, và là
nguyên nhân trực tiếp gây ra thương tật hoặc tử vong trong vòng một trăm tám
mươi (180) ngày kể từ ngày xảy ra sự kiện đó.

**Thương tật toàn bộ vĩnh viễn** là tình trạng thương tật khiến Người được bảo
hiểm mất hoàn toàn và vĩnh viễn khả năng lao động, được cơ sở y tế có thẩm quyền
xác nhận và kéo dài liên tục ít nhất một trăm tám mươi (180) ngày kể từ ngày xảy
ra sự kiện.

**Thời gian chờ** là khoảng thời gian tính từ Ngày hiệu lực hợp đồng mà trong đó
Công ty chưa phát sinh trách nhiệm chi trả đối với một số quyền lợi nhất định.

### Điều 2: Đối tượng và điều kiện tham gia

Người được bảo hiểm phải có Tuổi bảo hiểm từ mười tám (18) đến sáu mươi (60) tại
thời điểm giao kết Hợp đồng và phải được Công ty chấp nhận bảo hiểm sau khi thẩm
định. Hợp đồng có Thời hạn hợp đồng tối thiểu mười (10) năm.

Việc chấp nhận bảo hiểm có thể kèm theo điều kiện riêng đối với từng Hợp đồng,
bao gồm tăng phí bảo hiểm, giảm Số tiền bảo hiểm hoặc áp dụng điểm loại trừ bổ
sung theo quy định tại Điều 10 của Quy tắc, Điều khoản này.

## Chương II: Quyền lợi bảo hiểm

### Điều 3: Quyền lợi tử vong

Nếu Người được bảo hiểm tử vong trong Thời hạn hợp đồng và Hợp đồng đang có hiệu
lực, Công ty chi trả một trăm phần trăm (100%) Số tiền bảo hiểm ghi trên Giấy
chứng nhận bảo hiểm, cộng khoản lãi chia tích lũy (nếu có), sau khi trừ các
khoản nợ phát sinh từ Hợp đồng.

Quyền lợi tử vong được chi trả không phụ thuộc nguyên nhân tử vong là do bệnh
tật hay do tai nạn, ngoại trừ các trường hợp quy định tại Chương III.

### Điều 4: Quyền lợi thương tật toàn bộ vĩnh viễn

Nếu Người được bảo hiểm bị Thương tật toàn bộ vĩnh viễn trong Thời hạn hợp đồng
và Hợp đồng đang có hiệu lực, Công ty chi trả một trăm phần trăm (100%) Số tiền
bảo hiểm và Hợp đồng chấm dứt hiệu lực kể từ ngày Công ty chấp thuận chi trả.

Quyền lợi quy định tại Điều này và quyền lợi tử vong quy định tại Điều 3 chỉ
được chi trả một (01) lần cho mỗi Người được bảo hiểm.

### Điều 5: Quyền lợi đáo hạn

Nếu Người được bảo hiểm còn sống đến ngày kết thúc Thời hạn hợp đồng và Hợp đồng
đang có hiệu lực, Công ty chi trả một trăm phần trăm (100%) Số tiền bảo hiểm
cộng toàn bộ khoản lãi chia tích lũy đến thời điểm đáo hạn.

### Điều 6: Các quyền lợi không thuộc sản phẩm chính

Sản phẩm chính "An Vui Toàn Diện" chi trả các quyền lợi quy định tại Điều 3,
Điều 4 và Điều 5. Các quyền lợi trợ cấp nằm viện, chi phí phẫu thuật, thương tật
bộ phận do tai nạn và chăm sóc sức khỏe không thuộc sản phẩm chính; các quyền lợi
đó chỉ phát sinh khi Bên mua bảo hiểm tham gia sản phẩm bổ trợ tương ứng và sản
phẩm bổ trợ đó đang có hiệu lực.

Quyền lợi, điều kiện chi trả và điểm loại trừ của từng sản phẩm bổ trợ được quy
định tại Quy tắc, Điều khoản riêng của sản phẩm bổ trợ đó, không quy định tại
Quy tắc, Điều khoản này.

## Chương III: Loại trừ trách nhiệm bảo hiểm

### Điều 7: Các trường hợp loại trừ chung

Công ty không chi trả bất kỳ quyền lợi bảo hiểm nào nếu sự kiện bảo hiểm xảy ra
thuộc một trong các trường hợp sau đây:

1. Người được bảo hiểm tự tử trong vòng hai mươi bốn (24) tháng kể từ Ngày hiệu
lực hợp đồng hoặc kể từ ngày khôi phục hiệu lực gần nhất, không phụ thuộc vào
tình trạng tinh thần của Người được bảo hiểm tại thời điểm đó.

2. Người được bảo hiểm tử vong hoặc bị thương tật do hành vi cố ý của Bên mua
bảo hiểm, của Người được bảo hiểm hoặc của Người thụ hưởng nhằm trục lợi bảo
hiểm.

3. Sự kiện bảo hiểm phát sinh trong khi Người được bảo hiểm đang thực hiện hành
vi vi phạm pháp luật hình sự, đang bị tạm giam hoặc đang chấp hành hình phạt tù
theo bản án đã có hiệu lực pháp luật.

4. Sự kiện bảo hiểm phát sinh do chiến tranh, nội chiến, đình công, bạo loạn,
khủng bố có tổ chức, hoặc do nhiễm phóng xạ, nhiễm độc từ nhiên liệu hạt nhân
hoặc chất thải hạt nhân.

5. Người được bảo hiểm sử dụng ma túy, chất gây nghiện trái quy định của pháp
luật, hoặc sử dụng thuốc không theo chỉ định của cơ sở y tế có thẩm quyền.

6. Người được bảo hiểm nhiễm HIV hoặc mắc các bệnh liên quan đến HIV/AIDS, trừ
trường hợp lây nhiễm trong khi thực hiện nhiệm vụ nghề nghiệp được cơ quan có
thẩm quyền xác nhận.

### Điều 8: Loại trừ riêng đối với sự kiện do tai nạn

Ngoài các trường hợp quy định tại Điều 7, Công ty không chi trả quyền lợi bảo
hiểm đối với sự kiện phát sinh do tai nạn trong các trường hợp sau đây:

1. Người được bảo hiểm điều khiển phương tiện giao thông mà trong máu hoặc khí
thở có nồng độ cồn vượt quá mức cho phép theo quy định của pháp luật Việt Nam,
hoặc điều khiển phương tiện giao thông khi không có giấy phép lái xe hợp lệ đối
với loại phương tiện đó.

2. Người được bảo hiểm tham gia đua xe, đua thuyền, đua ngựa dưới mọi hình thức,
kể cả khi luyện tập.

3. Người được bảo hiểm tham gia thi đấu hoặc luyện tập chuyên nghiệp các môn thể
thao đối kháng, quyền anh, võ thuật thi đấu, nhảy dù, dù lượn, leo núi có sử
dụng dây bảo hộ chuyên dụng, hoặc lặn biển có bình khí.

4. Người được bảo hiểm tham gia chuyến bay không phải với tư cách hành khách có
vé trên chuyến bay thương mại của hãng hàng không được cấp phép, hoặc tham gia
huấn luyện bay dưới mọi hình thức.

5. Người được bảo hiểm bị thương tật hoặc tử vong trong khi tham gia đánh nhau,
trừ trường hợp tự vệ chính đáng được cơ quan có thẩm quyền xác nhận.

Các trường hợp loại trừ nêu tại Điều này chỉ áp dụng khi sự kiện bảo hiểm thực
tế thỏa mãn đúng điều kiện mô tả tại khoản tương ứng.

### Điều 9: Thời gian chờ đối với quyền lợi liên quan đến bệnh tật

Công ty không chi trả quyền lợi bảo hiểm đối với sự kiện bảo hiểm phát sinh do
bệnh tật trong thời gian chờ ba mươi (30) ngày kể từ Ngày hiệu lực hợp đồng,
hoặc ba trăm sáu mươi lăm (365) ngày đối với bệnh đặc biệt và bệnh có sẵn được
Công ty liệt kê tại Phụ lục Hợp đồng.

Thời gian chờ quy định tại Điều này không áp dụng đối với sự kiện bảo hiểm phát
sinh do tai nạn.

### Điều 10: Loại trừ bổ sung theo kết quả thẩm định

Ngoài các trường hợp loại trừ quy định tại Điều 7, Điều 8 và Điều 9, Công ty có
thể áp dụng các điểm loại trừ bổ sung đối với từng Hợp đồng cụ thể, căn cứ kết
quả thẩm định rủi ro tại thời điểm phát hành Hợp đồng, khi Người được bảo hiểm
có tình trạng sức khỏe dưới chuẩn, có bệnh lý sẵn có, hoặc có yếu tố rủi ro nghề
nghiệp dưới chuẩn.

Nội dung, phạm vi và thời hạn của từng điểm loại trừ bổ sung được ghi rõ trong
Giấy chứng nhận bảo hiểm hoặc Phụ lục Hợp đồng của chính Hợp đồng đó, và chỉ có
hiệu lực đối với Hợp đồng đó. Điểm loại trừ bổ sung không được suy diễn hoặc áp
dụng cho một Hợp đồng khác.

Ngoài các trường hợp được liệt kê tại Chương này và các điểm loại trừ bổ sung
được ghi trên Giấy chứng nhận bảo hiểm, Công ty không viện dẫn bất kỳ lý do nào
khác để từ chối chi trả quyền lợi bảo hiểm.

## Chương IV: Phí bảo hiểm và giá trị hợp đồng

### Điều 11: Phí bảo hiểm và định kỳ đóng phí

Phí bảo hiểm được xác định căn cứ vào Tuổi bảo hiểm, giới tính, Số tiền bảo hiểm,
Thời hạn hợp đồng và kết quả thẩm định rủi ro. Bên mua bảo hiểm lựa chọn định kỳ
đóng phí năm, nửa năm hoặc quý và duy trì định kỳ đó trong suốt Thời hạn hợp
đồng, trừ khi có thỏa thuận khác bằng văn bản.

### Điều 12: Thời gian gia hạn đóng phí

Bên mua bảo hiểm được gia hạn đóng phí bảo hiểm trong sáu mươi (60) ngày kể từ
ngày đến hạn đóng phí. Trong thời gian gia hạn, Hợp đồng vẫn có hiệu lực và Công
ty vẫn chi trả quyền lợi bảo hiểm khi sự kiện bảo hiểm xảy ra, sau khi trừ phần
phí bảo hiểm còn thiếu.

Nếu hết thời gian gia hạn mà Bên mua bảo hiểm vẫn chưa đóng đủ phí, Hợp đồng mất
hiệu lực, trừ trường hợp Hợp đồng đã có Giá trị hoàn lại đủ để tự động tạm ứng
đóng phí.

### Điều 13: Giá trị hoàn lại

Hợp đồng bắt đầu có Giá trị hoàn lại kể từ khi Bên mua bảo hiểm đã đóng đủ phí
bảo hiểm của hai (02) năm hợp đồng đầu tiên và Hợp đồng đang có hiệu lực. Giá
trị hoàn lại tại thời điểm kết thúc năm hợp đồng thứ $t$ được xác định theo công
thức:

$$GTHL_t = S \cdot r_t - L_t$$

trong đó $GTHL_t$ là Giá trị hoàn lại, $S$ là Số tiền bảo hiểm, $r_t$ là tỷ lệ
giá trị hoàn lại của năm hợp đồng thứ $t$ theo bảng đính kèm Hợp đồng, và $L_t$
là tổng các khoản nợ của Hợp đồng tại thời điểm đó.

## Chương V: Thủ tục giải quyết quyền lợi bảo hiểm

### Điều 14: Thông báo sự kiện bảo hiểm

Bên mua bảo hiểm, Người được bảo hiểm hoặc Người thụ hưởng phải thông báo cho
Công ty bằng văn bản trong vòng ba mươi (30) ngày kể từ ngày xảy ra sự kiện bảo
hiểm hoặc kể từ ngày biết về sự kiện bảo hiểm.

### Điều 15: Hồ sơ yêu cầu giải quyết quyền lợi

Hồ sơ yêu cầu giải quyết quyền lợi bảo hiểm bao gồm: Giấy yêu cầu giải quyết
quyền lợi bảo hiểm theo mẫu của Công ty; bản sao Giấy chứng nhận bảo hiểm; giấy
tờ tùy thân của Người thụ hưởng; và các chứng từ y tế, chứng từ pháp lý chứng
minh sự kiện bảo hiểm và nguyên nhân của sự kiện đó.

Đối với sự kiện bảo hiểm do tai nạn, hồ sơ còn bao gồm biên bản của cơ quan có
thẩm quyền về vụ tai nạn, trong đó nêu rõ nguyên nhân, hoàn cảnh xảy ra tai nạn
và kết luận về lỗi của các bên liên quan (nếu có).

### Điều 16: Thời hạn giải quyết

Công ty giải quyết và chi trả quyền lợi bảo hiểm trong vòng ba mươi (30) ngày kể
từ ngày nhận đủ hồ sơ hợp lệ. Trường hợp cần xác minh thêm, thời hạn giải quyết
không quá bốn mươi lăm (45) ngày kể từ ngày nhận đủ hồ sơ hợp lệ.
"""


DOCUMENTS: dict[str, str] = {
    "quy_tac_tu_ky_an_tam.md": POLICY_TERM_LIFE,
    "quy_tac_tron_doi_an_binh.md": POLICY_WHOLE_LIFE,
    "huong_dan_du_phong_toan_hoc.md": DOC_RESERVES,
    "cong_thuc_nien_kim_bang_ty_le_tu_vong.md": ANNUITY_MORTALITY,
    "quy_trinh_giai_quyet_quyen_loi.md": PROCEDURE_CLAIMS,
    "quy_tac_lien_ket_chung_an_phu.md": POLICY_UL_AN_PHU,
    "quy_tac_hon_hop_an_vui.md": POLICY_ENDOWMENT_AN_VUI,
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
