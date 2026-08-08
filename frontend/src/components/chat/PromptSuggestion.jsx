import React from "react";
export function PromptSuggestion({ eyebrow, title, onClick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ textAlign: "left", border: "1px solid " + (hover ? "var(--border-strong)" : "var(--border)"), background: "var(--surface)", borderRadius: "var(--radius-lg)", padding: "var(--space-3) var(--space-4)", cursor: "pointer", fontFamily: "var(--font-sans)", boxShadow: hover ? "var(--shadow-md)" : "var(--shadow-sm)", transform: hover ? "translateY(-1px)" : "none", transition: "box-shadow 180ms cubic-bezier(.2,.8,.2,1), transform 180ms cubic-bezier(.2,.8,.2,1), border-color 180ms" }}>
      {eyebrow && <div style={{ fontSize: "var(--text-2xs)", fontWeight: "var(--weight-bold)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--tracking-wide)", marginBottom: "var(--space-1)" }}>{eyebrow}</div>}
      <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)", color: "var(--text-primary)", lineHeight: "var(--leading-snug)" }}>{title}</div>
    </button>
  );
}
