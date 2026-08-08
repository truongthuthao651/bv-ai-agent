import React from "react";

export function Card({ title, hint, children, size = "md", style }) {
  return (
    <section style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)", borderRadius: "var(--radius-xl)", padding: size === "lg" ? "var(--pad-card-lg)" : "var(--pad-card)", ...style }}>
      {title && <h2 style={{ margin: 0, fontSize: "var(--text-md)", color: "var(--text-primary)", fontWeight: "var(--weight-semibold)", letterSpacing: "var(--tracking-tight)" }}>{title}</h2>}
      {hint && <p style={{ margin: "var(--space-1) 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)", lineHeight: "var(--leading-snug)" }}>{hint}</p>}
      {(title || hint) && <div style={{ height: "var(--space-5)" }} />}
      {children}
    </section>
  );
}
