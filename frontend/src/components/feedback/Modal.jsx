import React, { useEffect, useId } from "react";

export function Modal({ open, title, hint, children, onClose, actions }) {
  const titleId = useId();
  // P2-C3 (audit/REPORT.md): the only prior dismiss path was clicking the
  // backdrop — no Escape handling at all, which is the standard expectation
  // for any modal. One listener here benefits every Modal in the app at once.
  useEffect(() => {
    if (!open) return;
    function onKeyDown(e) {
      if (e.key === "Escape") onClose?.();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(12,42,69,.55)", backdropFilter: "blur(2px)", display: "flex", alignItems: "center", justifyContent: "center", padding: "var(--space-5)", zIndex: 50 }} onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby={title ? titleId : undefined} style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: "var(--radius-xl)", width: "100%", maxWidth: 480, padding: "var(--pad-card-lg)", boxShadow: "var(--shadow-lg)" }}>
        {title && <h3 id={titleId} style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", letterSpacing: "var(--tracking-tight)" }}>{title}</h3>}
        {hint && <p style={{ margin: "var(--space-1) 0 0", fontSize: "var(--text-sm)", color: "var(--text-secondary)", lineHeight: "var(--leading-normal)" }}>{hint}</p>}
        <div style={{ marginTop: "var(--space-5)" }}>{children}</div>
        {actions && <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-2)", marginTop: "var(--space-6)" }}>{actions}</div>}
      </div>
    </div>
  );
}
