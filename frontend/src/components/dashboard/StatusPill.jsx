import React from "react";
const TONE = {
  indexed: { bg: "color-mix(in srgb, var(--success) 14%, transparent)", fg: "var(--success)", dot: "var(--success)" },
  processing: { bg: "color-mix(in srgb, var(--accent) 14%, transparent)", fg: "var(--accent)", dot: "var(--accent)" },
  failed: { bg: "color-mix(in srgb, var(--danger) 14%, transparent)", fg: "var(--danger)", dot: "var(--danger)" },
  queued: { bg: "var(--surface-sunken)", fg: "var(--text-secondary)", dot: "var(--text-muted)" },
};
export function StatusPill({ status, label }) {
  const t = TONE[status] || TONE.queued;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)", padding: "var(--space-1) var(--space-3)", borderRadius: "var(--radius-pill)", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", background: t.bg, color: t.fg }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: t.dot, flexShrink: 0 }} />
      {label}
    </span>
  );
}
