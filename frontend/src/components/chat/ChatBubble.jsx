import React from "react";
export function ChatBubble({ role = "assistant", children }) {
  const isUser = role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start" }}>
      <div style={{ maxWidth: "72%", padding: "var(--space-3) var(--space-4)", borderRadius: "var(--radius-lg)", fontSize: "var(--text-md)", lineHeight: "var(--leading-normal)", whiteSpace: "pre-wrap", background: isUser ? "var(--accent)" : "var(--surface)", color: isUser ? "var(--text-on-accent)" : "var(--text-primary)", border: isUser ? "none" : "1px solid var(--border)" }}>
        {children}
      </div>
    </div>
  );
}
