/** Department labels — mirrors app/department_labels.py (keep in sync). */

export const DEPARTMENT_LABELS = {
  PTSP: "Phát triển sản phẩm",
  DP: "Điều phối",
  DVA: "Dịch vụ & vận hành",
};

export function departmentLabel(code) {
  if (!code) return "—";
  return DEPARTMENT_LABELS[code] ?? code;
}

export function departmentOptionLabel(code) {
  const label = DEPARTMENT_LABELS[code];
  return label ? `${code} — ${label}` : code;
}

export function departmentDisplay(code) {
  if (!code) return "—";
  const label = DEPARTMENT_LABELS[code];
  return label ? `${code} — ${label}` : code;
}
