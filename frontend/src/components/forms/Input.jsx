import React from "react";

/** Shared control geometry: matches Button at the same `size`, so form rows align. */
const HEIGHTS = { sm: "var(--control-h-sm)", md: "var(--control-h-md)", lg: "var(--control-h-lg)" };
const FONTS = { sm: "var(--text-xs)", md: "var(--text-sm)", lg: "var(--text-base)" };
const field = (size) => ({
  fontFamily: "var(--font-sans)", fontSize: FONTS[size], height: HEIGHTS[size],
  padding: "0 var(--pad-control-x)", borderRadius: "var(--radius-md)",
  border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text-primary)",
  boxSizing: "border-box", transition: "border-color 150ms, box-shadow 150ms",
});

export function Input({ value, onChange, placeholder, type = "text", size = "md", disabled, style, ...rest }) {
  return <input type={type} value={value} onChange={onChange} placeholder={placeholder} disabled={disabled} {...rest}
    style={{ ...field(size), width: "100%", ...(disabled ? { background: "var(--surface-sunken)", color: "var(--text-muted)", cursor: "not-allowed" } : null), ...style }} />;
}

export function Select({ value, onChange, children, size = "md", disabled, style }) {
  return <select value={value} onChange={onChange} disabled={disabled} style={{ ...field(size), cursor: disabled ? "not-allowed" : "pointer", ...style }}>{children}</select>;
}

export function Textarea({ value, onChange, placeholder, rows = 4, style }) {
  return <textarea value={value} onChange={onChange} placeholder={placeholder} rows={rows}
    style={{ ...field("md"), height: "auto", width: "100%", padding: "var(--pad-control-y) var(--pad-control-x)", lineHeight: "var(--leading-normal)", resize: "vertical", ...style }} />;
}

export function Dropzone({ label = "Kéo thả tệp vào đây, hoặc bấm để chọn", hint, onClick, dragging = false, ...rest }) {
  return (
    <div onClick={onClick} {...rest} style={{ border: `2px dashed ${dragging ? "var(--accent)" : "var(--border-strong)"}`, background: dragging ? "var(--accent-subtle)" : "transparent", borderRadius: "var(--radius-lg)", padding: "var(--space-8)", textAlign: "center", cursor: "pointer", transition: "border-color 150ms, background 150ms" }}>
      <p style={{ margin: 0, color: "var(--text-primary)", fontWeight: "var(--weight-semibold)", fontSize: "var(--text-sm)" }}>{label}</p>
      {hint && <p style={{ margin: "var(--space-1) 0 0", color: "var(--text-muted)", fontSize: "var(--text-xs)" }}>{hint}</p>}
    </div>
  );
}
