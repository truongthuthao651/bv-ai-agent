"""Human-readable labels for ``settings.departments`` codes.

Canonical source — keep ``frontend/src/admin/departmentLabels.js`` in sync.
"""

from __future__ import annotations

# code -> short Vietnamese department name
DEPARTMENT_LABELS: dict[str, str] = {
    "PTSP": "Phát triển sản phẩm",
    "DP": "Điều phối",
    "DVA": "Dịch vụ & vận hành",
}


def department_label(code: str | None) -> str:
    if not code:
        return "—"
    return DEPARTMENT_LABELS.get(code, code)


def department_option_label(code: str) -> str:
    """Select option: ``PTSP — Phát triển sản phẩm``."""
    label = DEPARTMENT_LABELS.get(code)
    return f"{code} — {label}" if label else code


def department_display(code: str | None) -> str:
    if not code:
        return "—"
    label = DEPARTMENT_LABELS.get(code)
    return f"{code} — {label}" if label else code
