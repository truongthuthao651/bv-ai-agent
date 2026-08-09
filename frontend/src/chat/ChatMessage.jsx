import { useState } from "react";
import { Triangle } from "../brand/Triangle.jsx";
import { Button } from "../components/index.js";
import { renderMarkdown, splitSources, citedSourcesOnly } from "./markdown.jsx";

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

function MessageActions({ text, onRegenerate, onFeedback, feedbackSent }) {
  const [copied, setCopied] = useState(false);
  const btnStyle = { height: 28, padding: "0 var(--space-2)", color: "var(--text-muted)", fontSize: "var(--text-2xs)", border: "none" };
  return (
    <div style={{ display: "flex", gap: "var(--space-1)", marginTop: "var(--space-3)", marginLeft: "calc(var(--space-2) * -1)" }}>
      <Button
        variant="ghost"
        style={btnStyle}
        onClick={() => {
          navigator.clipboard?.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? "Đã chép" : "Chép"}
      </Button>
      {onRegenerate && (
        <Button variant="ghost" style={btnStyle} onClick={onRegenerate}>
          Tạo lại
        </Button>
      )}
      {onFeedback && (
        // P2-F2 (audit/REPORT.md): the only quality signal this app has in
        // production beyond eval/'s golden set — flags this answer without
        // sending its text anywhere (see chat/api.js's sendFeedback).
        <Button
          variant="ghost"
          style={btnStyle}
          onClick={onFeedback}
          disabled={feedbackSent}
          title="Báo câu trả lời này chưa đúng"
          aria-label="Báo câu trả lời này chưa đúng"
        >
          {feedbackSent ? "Đã báo" : "👎 Chưa đúng"}
        </Button>
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

/** Shown in the empty assistant bubble between send and the first streamed
 * token — retrieval + rerank alone routinely takes 8-50s (audit/04-chatbot.md
 * §4.2), during which the bubble previously showed nothing at all beyond the
 * composer's send button greying out. Text label first (works even if
 * animation is off); the dots are a secondary, reduced-motion-aware cue. */
function ThinkingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", color: "var(--text-secondary)", fontSize: "var(--text-md)" }}>
      <span>Đang tìm trong tài liệu…</span>
      <span style={{ display: "inline-flex", gap: 3 }}>
        <span className="bv-thinking-dot" style={{ animationDelay: "0ms" }} />
        <span className="bv-thinking-dot" style={{ animationDelay: "160ms" }} />
        <span className="bv-thinking-dot" style={{ animationDelay: "320ms" }} />
      </span>
      <style>{`
        .bv-thinking-dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: currentColor;
          display: inline-block;
          animation: bv-thinking-pulse 1.2s ease-in-out infinite;
        }
        @keyframes bv-thinking-pulse {
          0%, 80%, 100% { opacity: 0.25; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
        @media (prefers-reduced-motion: reduce) {
          .bv-thinking-dot { animation: none; opacity: 0.6; }
        }
      `}</style>
    </div>
  );
}

export function ChatMessage({ role, text, streaming, active, onOpen, onRegenerate, onFeedback, feedbackSent }) {
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
  const { body, citations: allCitations } = streaming ? { body: text, citations: [] } : splitSources(text);
  const citations = citedSourcesOnly(body, allCitations);

  return (
    <div style={{ display: "flex", gap: "var(--space-4)" }}>
      <div style={{ width: 28, height: 28, flexShrink: 0, borderRadius: "var(--radius-md)", background: "var(--brand-ink)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Triangle size={11} />
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        {isRefusal ? (
          <NoAnswer />
        ) : streaming && !body ? (
          <ThinkingIndicator />
        ) : (
          <>
            <div style={{ fontSize: "var(--text-md)", color: "var(--text-primary)" }}>{renderMarkdown(body || " ")}</div>
            {citations.length > 0 && <CitationRow citations={citations} active={active} onOpen={onOpen} />}
            {!streaming && (
              <MessageActions text={body} onRegenerate={onRegenerate} onFeedback={onFeedback} feedbackSent={feedbackSent} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
