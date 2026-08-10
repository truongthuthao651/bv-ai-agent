import React from "react";

/** Every variant ships default, hover, active, focus-visible and disabled.
 * `...rest` forwards anything else (aria-label, title, aria-hidden, id, ...)
 * onto the underlying <button> — needed for icon-only usage, where an
 * accessible name has to come from an attribute rather than visible text
 * (ENG-1, audit/REPORT.md: this was previously the reason /chat's icon
 * buttons couldn't adopt this component and stayed hand-rolled). */
export function Button({ children, variant = "primary", size = "md", disabled = false, onClick, type = "button", style, ...rest }) {
  const sizes = {
    sm: { height: "var(--control-h-sm)", padding: "0 var(--space-3)", fontSize: "var(--text-xs)" },
    md: { height: "var(--control-h-md)", padding: "0 var(--space-4)", fontSize: "var(--text-sm)" },
    lg: { height: "var(--control-h-lg)", padding: "0 var(--space-5)", fontSize: "var(--text-base)" },
  };
  const variants = {
    primary: { background: "var(--accent)", color: "var(--text-on-accent)", border: "1px solid transparent" },
    accent: { background: "var(--gold)", color: "var(--text-on-gold)", border: "1px solid transparent" },
    secondary: { background: "var(--surface)", color: "var(--text-primary)", border: "1px solid var(--border)" },
    outline: { background: "transparent", color: "var(--accent)", border: "1px solid var(--accent)" },
    danger: { background: "var(--danger-subtle)", color: "var(--danger)", border: "1px solid transparent" },
    ghost: { background: "transparent", color: "var(--text-secondary)", border: "1px solid transparent" },
  };
  const hovers = {
    primary: { background: "var(--accent-hover)" },
    accent: { background: "var(--brand-gold-light)" },
    secondary: { background: "var(--hover)", borderColor: "var(--border-strong)" },
    outline: { background: "var(--accent-subtle)" },
    danger: { background: "var(--danger)", color: "#fff" },
    ghost: { background: "var(--hover)", color: "var(--text-primary)" },
  };
  const [hover, setHover] = React.useState(false);
  const [press, setPress] = React.useState(false);

  return (
    <button
      type={type} disabled={disabled} onClick={onClick}
      className="bv-focus-ring"
      onMouseEnter={() => setHover(true)} onMouseLeave={() => { setHover(false); setPress(false); }}
      onMouseDown={() => setPress(true)} onMouseUp={() => setPress(false)}
      {...rest}
      style={{
        fontFamily: "var(--font-sans)", fontWeight: "var(--weight-semibold)", borderRadius: "var(--radius-md)",
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "var(--space-2)",
        whiteSpace: "nowrap", cursor: disabled ? "not-allowed" : "pointer",
        transition: "background 150ms cubic-bezier(.2,.8,.2,1), border-color 150ms, transform 100ms",
        ...sizes[size], ...variants[variant],
        ...(hover && !disabled ? hovers[variant] : null),
        ...(press && !disabled ? { transform: "translateY(1px)" } : null),
        ...(disabled ? { opacity: 0.45, background: "var(--surface-sunken)", color: "var(--text-muted)", borderColor: "var(--border)" } : null),
        ...style,
      }}>
      {children}
    </button>
  );
}
