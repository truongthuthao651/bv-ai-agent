from app.department_labels import (
    department_display,
    department_label,
    department_option_label,
)


def test_department_label_known_codes() -> None:
    assert department_label("PTSP") == "Phát triển sản phẩm"
    assert department_display("DP") == "DP — Điều phối"
    assert department_option_label("DVA") == "DVA — Dịch vụ & vận hành"


def test_department_label_unknown_code_passthrough() -> None:
    assert department_label("XYZ") == "XYZ"
    assert department_display("XYZ") == "XYZ"
