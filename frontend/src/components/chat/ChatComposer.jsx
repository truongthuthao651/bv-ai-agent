import React from "react";
import { Icon } from "../icons/Icon.jsx";

/** Elevated composer bar: multiline input plus the controls that change the next answer. */
export function ChatComposer({ value, onChange, onSend, placeholder = "Ask about a policy, procedure, or formula…", scope = "All documents", model = "Qwen3 8B", children }) {
  const [focus, setFocus] = React.useState(false);
  const ctl = { display: "inline-flex", alignItems: "center", gap: "var(--space-2)", height: "var(--control-h-sm)", padding: "0 var(--space-3)", border: "none", background: "transparent", borderRadius: "var(--radius-md)", fontFamily: "var(--font-sans)", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-secondary)", cursor: "pointer" };
  return (
    <div style={{ background: "var(--surface-raised)", border: "1px solid " + (focus ? "var(--accent)" : "var(--border)"), borderRadius: "var(--radius-xl)", boxShadow: focus ? "var(--shadow-lg), 0 0 0 3px var(--accent-subtle)" : "var(--shadow-md)", padding: "var(--space-3)", transition: "border-color 150ms, box-shadow 150ms" }}>
      {children}
      <textarea
        value={value} onChange={onChange} rows={2} placeholder={placeholder}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={{ width: "100%", boxSizing: "border-box", border: "none", outline: "none", resize: "none", background: "transparent", fontFamily: "var(--font-sans)", fontSize: "var(--text-md)", lineHeight: "var(--leading-normal)", color: "var(--text-primary)", padding: "var(--space-2) var(--space-3)" }} />
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
        <button style={ctl} title="Attach PDF, Word, Excel or an image"><Icon name="plus" size={14} /> Attach</button>
        <button style={ctl} title="Which document set is searched">Scope: {scope} <Icon name="chevron-down" size={12} color="var(--text-muted)" /></button>
        <button style={ctl} title="Answering model — runs on the internal server">{model} <Icon name="chevron-down" size={12} color="var(--text-muted)" /></button>
        <button onClick={onSend} disabled={!value} title="Send"
          style={{ marginLeft: "auto", width: 36, height: 36, borderRadius: "var(--radius-md)", border: "none", background: value ? "var(--accent)" : "var(--surface-sunken)", color: value ? "var(--text-on-accent)" : "var(--text-muted)", cursor: value ? "pointer" : "not-allowed", display: "flex", alignItems: "center", justifyContent: "center", transition: "background 150ms" }}>
          <Icon name="arrow-up" size={16} />
        </button>
      </div>
    </div>
  );
}
