import React from "react";

/** Status pill. Defaults to the light-surface treatment; `onDark` for navy headers. */
export function Badge({ label, status = "neutral", onDark = false }) {
  const dot = { ok: "var(--success)", bad: "var(--danger)", neutral: "var(--text-muted)" }[status];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)", padding: "var(--space-1) var(--space-3)", borderRadius: "var(--radius-pill)", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", background: onDark ? "rgba(255,255,255,.14)" : "var(--surface-sunken)", color: onDark ? "#fff" : "var(--text-secondary)" }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: dot, flexShrink: 0 }} />
      {label}
    </span>
  );
}

export function Tag({ children, tone = "info" }) {
  const tones = {
    info: { background: "var(--accent-subtle)", color: "var(--accent)" },
    muted: { background: "var(--surface-sunken)", color: "var(--text-secondary)" },
  };
  return <span style={{ display: "inline-block", padding: "var(--space-half) var(--space-2)", borderRadius: "var(--radius-sm)", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", ...tones[tone] }}>{children}</span>;
}
