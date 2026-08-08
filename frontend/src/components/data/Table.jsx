import React from "react";

/** Rows highlight on hover; header and cells sit on --pad-cell-y/x. */
export function Table({ columns, rows, renderRow, emptyLabel = "Không có dữ liệu." }) {
  const [hover, setHover] = React.useState(null);
  const cell = { padding: "var(--pad-cell-y) var(--pad-cell-x)", borderBottom: "1px solid var(--border)" };
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--text-sm)", color: "var(--text-primary)" }}>
      <thead>
        <tr>{columns.map((c, i) => (
          <th key={i} style={{ ...cell, textAlign: "left", color: "var(--text-muted)", fontWeight: "var(--weight-bold)", fontSize: "var(--text-2xs)", textTransform: "uppercase", letterSpacing: "var(--tracking-wide)" }}>{c}</th>
        ))}</tr>
      </thead>
      <tbody>
        {rows.length === 0
          ? <tr><td colSpan={columns.length} style={{ color: "var(--text-muted)", textAlign: "center", padding: "var(--space-6) 0" }}>{emptyLabel}</td></tr>
          : rows.map((row, i) => (
            <tr key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
              style={{ background: hover === i ? "var(--hover)" : "transparent", transition: "background 120ms" }}>
              {renderRow(row, i).map((c, j) => <td key={j} style={cell}>{c}</td>)}
            </tr>
          ))}
      </tbody>
    </table>
  );
}

export function StatTile({ value, label }) {
  return (
    <div style={{ background: "var(--surface-sunken)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", padding: "var(--space-3) var(--space-4)" }}>
      <div style={{ fontSize: "var(--text-2xl)", fontWeight: "var(--weight-bold)", color: "var(--text-primary)", lineHeight: "var(--leading-tight)", fontVariantNumeric: "tabular-nums" }}>{value}</div>
      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginTop: "var(--space-1)" }}>{label}</div>
    </div>
  );
}
