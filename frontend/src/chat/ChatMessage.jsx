import { useState } from "react";
import { Triangle } from "../brand/Triangle.jsx";
import { renderMarkdown, splitSources } from "./markdown.jsx";

const REFUSAL_TEXT = "Tôi không tìm thấy thông tin trong tài liệu.";

function CitationRow({ citations, active, onOpen }) {
  return (
    <div style={{ marginTop: "var(--space-4)" }}>
      <div style={{ fontSize: "var(--text-2xs)", fontWeight: "var(--weight-bold)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--tracking-wide)", marginBottom: "var(--space-2)" }}>
        Nguồn · {citations.length}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
        {citations.map((c) => {
          const on = active && active.n === c.n;
          return (
            <button
              key={c.n}
              onClick={() => onOpen(c)}
              title={c.title}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "var(--space-2)",
                maxWidth: 300,
                height: "var(--control-h-sm)",
                padding: "0 var(--space-3) 0 var(--space-1)",
                borderRadius: "var(--radius-md)",
                border: "1px solid " + (on ? "var(--accent)" : "var(--border)"),
                background: on ? "var(--accent-subtle)" : "var(--surface)",
                cursor: "pointer",
                fontFamily: "var(--font-sans)",
              }}
            >
              <span
                style={{
                  width: 22,
                  height: 22,
                  flexShrink: 0,
                  borderRadius: "var(--radius-sm)",
                  background: on ? "var(--accent)" : "var(--surface-sunken)",
                  color: on ? "var(--text-on-accent)" : "var(--text-secondary)",
                  fontSize: "var(--text-2xs)",
                  fontWeight: "var(--weight-bold)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {c.n}
              </span>
              <span style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-medium)", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {c.title}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function MessageActions({ text, onRegenerate }) {
  const [copied, setCopied] = useState(false);
  const btn = { display: "inline-flex", alignItems: "center", gap: "var(--space-1)", height: 28, padding: "0 var(--space-2)", border: "none", background: "transparent", color: "var(--text-muted)", fontFamily: "var(--font-sans)", fontSize: "var(--text-2xs)", fontWeight: "var(--weight-semibold)", borderRadius: "var(--radius-sm)", cursor: "pointer" };
  return (
    <div style={{ display: "flex", gap: "var(--space-1)", marginTop: "var(--space-3)", marginLeft: "calc(var(--space-2) * -1)" }}>
      <button
        style={btn}
        onClick={() => {
          navigator.clipboard?.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? "Đã chép" : "Chép"}
      </button>
      {onRegenerate && (
        <button style={btn} onClick={onRegenerate}>
          Tạo lại
        </button>
      )}
    </div>
  );
}

function NoAnswer() {
  return (
    <p style={{ margin: 0, fontSize: "var(--text-md)", lineHeight: "var(--leading-normal)", color: "var(--text-primary)" }}>
      Tôi không tìm thấy thông tin này trong các tài liệu bạn có quyền truy cập. Hãy thử nêu rõ tên sản phẩm, hoặc diễn đạt lại câu hỏi.
    </p>
  );
}

export function ChatMessage({ role, text, streaming, active, onOpen, onRegenerate }) {
  if (role === "user") {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <div
          style={{
            maxWidth: "76%",
            background: "var(--accent)",
            color: "var(--text-on-accent)",
            padding: "var(--space-3) var(--space-4)",
            borderRadius: "var(--radius-xl) var(--radius-xl) var(--radius-sm) var(--radius-xl)",
            fontSize: "var(--text-md)",
          }}
        >
          {renderMarkdown(text)}
        </div>
      </div>
    );
  }

  // Every finished answer gets a "\n\n_⏱ Thời gian trả lời: Ns_" footer
  // appended server-side (app/query_timing.py's response_time_footer),
  // refusals included — so an exact match against REFUSAL_TEXT alone was
  // never true in production and NoAnswer() below was dead code. Strip the
  // footer before comparing.
  const isRefusal =
    !streaming && text.replace(/\n\n_⏱[^_]*_\s*$/, "").trim() === REFUSAL_TEXT;
  const { body, citations } = streaming ? { body: text, citations: [] } : splitSources(text);

  return (
    <div style={{ display: "flex", gap: "var(--space-4)" }}>
      <div style={{ width: 28, height: 28, flexShrink: 0, borderRadius: "var(--radius-md)", background: "var(--brand-ink)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Triangle size={11} />
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        {isRefusal ? (
          <NoAnswer />
        ) : (
          <>
            <div style={{ fontSize: "var(--text-md)", color: "var(--text-primary)" }}>{renderMarkdown(body || " ")}</div>
            {citations.length > 0 && <CitationRow citations={citations} active={active} onOpen={onOpen} />}
            {!streaming && <MessageActions text={body} onRegenerate={onRegenerate} />}
          </>
        )}
      </div>
    </div>
  );
}
