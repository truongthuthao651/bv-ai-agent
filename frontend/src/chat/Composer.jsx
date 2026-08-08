import { useState } from "react";

/** Ported from ui_kits/chatbot/ChatParts.jsx's Composer. Attachment chips and
 * the "Scope"/model pickers are dropped — see the Phase 4 gap list: there is
 * no employee-facing ingest pipe (that endpoint is admin-only), and there is
 * only ever one model (settings.chat_model), so a picker with nothing to
 * pick would be exactly the "key hint that does nothing" the design system
 * warns against. The trust line is real, not decorative. */
export function Composer({ value, onChange, onSend, onStop, disabled, mobile }) {
  const [focus, setFocus] = useState(false);

  function submit() {
    if (!value.trim() || disabled) return;
    onSend();
  }

  return (
    <div style={{ padding: mobile ? "var(--space-3) var(--space-4) var(--space-4)" : "var(--space-4) var(--space-8) var(--space-5)", flexShrink: 0 }}>
      <div style={{ maxWidth: "var(--content-max)", margin: "0 auto" }}>
        <div
          style={{
            background: "var(--surface-raised)",
            border: "1px solid " + (focus ? "var(--accent)" : "var(--border)"),
            borderRadius: "var(--radius-xl)",
            boxShadow: focus ? "var(--shadow-lg), 0 0 0 3px var(--accent-subtle)" : "var(--shadow-md)",
            padding: "var(--space-3)",
            transition: "border-color 150ms, box-shadow 150ms",
          }}
        >
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            rows={2}
            onFocus={() => setFocus(true)}
            onBlur={() => setFocus(false)}
            placeholder="Hỏi về một quy tắc, quy trình, hoặc công thức…"
            style={{
              width: "100%",
              boxSizing: "border-box",
              border: "none",
              outline: "none",
              resize: "none",
              background: "transparent",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-md)",
              lineHeight: "var(--leading-normal)",
              color: "var(--text-primary)",
              padding: "var(--space-2) var(--space-3)",
            }}
          />
          <div style={{ display: "flex", alignItems: "center", marginTop: "var(--space-2)" }}>
            {disabled && onStop ? (
              // A generation is in flight — offer to cancel it instead of a
              // disabled, dead send button (CHAT-1, audit/REPORT.md): the
              // model's own answers routinely take 8-50s (audit/04-chatbot.md
              // §4.2), and until now there was no way to back out of a wrong
              // or regretted question short of closing the tab.
              <button
                onClick={onStop}
                title="Dừng"
                aria-label="Dừng tạo câu trả lời"
                style={{
                  marginLeft: "auto",
                  width: 36,
                  height: 36,
                  borderRadius: "var(--radius-md)",
                  border: "none",
                  background: "var(--danger)",
                  color: "var(--text-on-accent)",
                  cursor: "pointer",
                  fontSize: 15,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "background 150ms",
                }}
              >
                <span style={{ width: 10, height: 10, borderRadius: 2, background: "currentColor" }} />
              </button>
            ) : (
              <button
                onClick={submit}
                disabled={!value.trim() || disabled}
                title="Gửi"
                aria-label="Gửi câu hỏi"
                style={{
                  marginLeft: "auto",
                  width: 36,
                  height: 36,
                  borderRadius: "var(--radius-md)",
                  border: "none",
                  background: value.trim() && !disabled ? "var(--accent)" : "var(--surface-sunken)",
                  color: value.trim() && !disabled ? "var(--text-on-accent)" : "var(--text-muted)",
                  cursor: value.trim() && !disabled ? "pointer" : "not-allowed",
                  fontSize: 15,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "background 150ms",
                }}
              >
                ↑
              </button>
            )}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "var(--space-2)", marginTop: "var(--space-3)", fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--success)" }} />
          Dữ liệu của bạn nằm trong mạng nội bộ
        </div>
      </div>
    </div>
  );
}
