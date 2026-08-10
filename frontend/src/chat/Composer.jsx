import { useEffect, useRef, useState } from "react";
import { Button, Icon } from "../components/index.js";
import { useLocale } from "../i18n/LocaleContext.jsx";

/** Ported from ui_kits/chatbot/ChatParts.jsx's Composer. Employee-facing
 * attachment chips are dropped (ingest is admin-only); admins get an optional
 * `onUpload` hook rendered as a "+" beside the send row. Scope/model pickers
 * are also dropped — only one model (settings.chat_model). The trust line is
 * real, not decorative. */

const MAX_TEXTAREA_HEIGHT = 200;

export function Composer({ value, onChange, onSend, onStop, onUpload, disabled, mobile }) {
  const { t } = useLocale();
  const [focus, setFocus] = useState(false);
  const textareaRef = useRef(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT) + "px";
  }, [value]);

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
            ref={textareaRef}
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
            placeholder={t("chat.composerPlaceholder")}
            style={{
              width: "100%",
              boxSizing: "border-box",
              border: "none",
              outline: "none",
              resize: "none",
              overflowY: "auto",
              maxHeight: MAX_TEXTAREA_HEIGHT,
              background: "transparent",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-md)",
              lineHeight: "var(--leading-normal)",
              color: "var(--text-primary)",
              padding: "var(--space-2) var(--space-3)",
            }}
          />
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
            {onUpload && (
              <Button
                variant="ghost"
                onClick={onUpload}
                title={t("chat.uploadDocument")}
                aria-label={t("chat.uploadDocument")}
                style={{
                  width: 36,
                  height: 36,
                  padding: 0,
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-pill)",
                  fontSize: 20,
                  lineHeight: 1,
                  color: "var(--text-secondary)",
                }}
              >
                <Icon name="plus" size={18} />
              </Button>
            )}
            {disabled && onStop ? (
              <Button
                variant="danger"
                onClick={onStop}
                title={t("chat.stop")}
                aria-label={t("chat.stopAria")}
                style={{ marginLeft: "auto", width: 36, height: 36, padding: 0, border: "none" }}
              >
                <Icon name="square" size={12} />
              </Button>
            ) : (
              <Button
                variant="primary"
                onClick={submit}
                disabled={!value.trim() || disabled}
                title={t("chat.send")}
                aria-label={t("chat.sendAria")}
                style={{ marginLeft: "auto", width: 36, height: 36, padding: 0, border: "none", fontSize: 15 }}
              >
                <Icon name="arrow-up" size={16} />
              </Button>
            )}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "var(--space-2)", marginTop: "var(--space-3)", fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--success)" }} />
          {t("chat.trustLine")}
        </div>
      </div>
    </div>
  );
}
