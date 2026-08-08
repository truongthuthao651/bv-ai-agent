import React from "react";

/** Matches Button/Input at sm: --control-h-sm, so it lines up in a toolbar row.
 *  `iconOnly` is the 32px square used in both kit headers. */
export function ThemeToggle({ theme, onChange, iconOnly = false }) {
  const dark = theme === "dark";
  const [hover, setHover] = React.useState(false);
  return (
    <button onClick={() => onChange(dark ? "light" : "dark")} aria-label="Toggle theme" title={dark ? "Switch to light" : "Switch to dark"}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "var(--space-2)", height: "var(--control-h-sm)", width: iconOnly ? "var(--control-h-sm)" : "auto", padding: iconOnly ? 0 : "0 var(--pad-control-x)", borderRadius: iconOnly ? "var(--radius-md)" : "var(--radius-pill)", border: "1px solid var(--border)", background: hover ? "var(--hover)" : "var(--surface)", color: "var(--text-secondary)", cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", transition: "background 150ms" }}>
      <span aria-hidden="true">{dark ? "☾" : "☀"}</span>{!iconOnly && (dark ? "Dark" : "Light")}
    </button>
  );
}
