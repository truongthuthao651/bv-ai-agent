import { useState } from "react";
import { BrandGlobe } from "../brand/BrandGlobe.jsx";
import { Button, Icon } from "../components/index.js";
import { isRefusalAnswer } from "../i18n/catalog.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { renderMarkdown, splitSources, citedSourcesOnly } from "./markdown.jsx";

function CitationRow({ citations, active, onOpen }) {
  const { t } = useLocale();
  return (
    <div style={{ marginTop: "var(--space-4)" }}>
      <div style={{ fontSize: "var(--text-2xs)", fontWeight: "var(--weight-bold)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--tracking-wide)", marginBottom: "var(--space-2)" }}>
        {t("chat.sources")} · {citations.length}
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
  const { t } = useLocale();
  const [copied, setCopied] = useState(false);
  const btnStyle = { height: 28, padding: "0 var(--space-2)", color: "var(--text-muted)", fontSize: "var(--text-2xs)", border: "none" };

  function requestFeedback() {
    const feedback = window.prompt(t("chat.feedbackPrompt"));
    if (!feedback?.trim()) return;
    onFeedback(feedback.trim()).catch(() => window.alert(t("chat.feedbackSendFailed")));
  }

  return (
    <>
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
          {copied ? t("chat.copied") : t("chat.copy")}
        </Button>
        {onRegenerate && (
          <Button variant="ghost" style={btnStyle} onClick={onRegenerate}>
            {t("chat.regenerate")}
          </Button>
        )}
        {onFeedback && (
          <Button
            variant="ghost"
            style={btnStyle}
            onClick={requestFeedback}
            disabled={feedbackSent}
            title={t("chat.feedbackTitle")}
            aria-label={t("chat.feedbackTitle")}
          >
            {feedbackSent ? (
              t("chat.feedbackDone")
            ) : (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Icon name="thumbs-down" size={14} /> {t("chat.feedbackBad")}
              </span>
            )}
          </Button>
        )}
      </div>
    </>
  );
}

function NoAnswer() {
  const { t } = useLocale();
  return (
    <p style={{ margin: 0, fontSize: "var(--text-md)", lineHeight: "var(--leading-normal)", color: "var(--text-primary)" }}>
      {t("chat.noAnswer")}
    </p>
  );
}

function ThinkingIndicator() {
  const { t } = useLocale();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", color: "var(--text-secondary)", fontSize: "var(--text-md)" }}>
      <span>{t("chat.thinking")}</span>
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
  const { locale } = useLocale();

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

  const isRefusal = !streaming && isRefusalAnswer(text, locale);
  const { body, citations: allCitations, responseTime } = streaming ? { body: text, citations: [], responseTime: null } : splitSources(text);
  const citations = citedSourcesOnly(body, allCitations);

  return (
    <div style={{ display: "flex", gap: "var(--space-4)" }}>
      <BrandGlobe size={28} />
      <div style={{ minWidth: 0, flex: 1 }}>
        {isRefusal ? (
          <NoAnswer />
        ) : streaming && !body ? (
          <ThinkingIndicator />
        ) : (
          <>
            <div style={{ fontSize: "var(--text-md)", color: "var(--text-primary)" }}>{renderMarkdown(body || " ")}</div>
            {citations.length > 0 && <CitationRow citations={citations} active={active} onOpen={onOpen} />}
            {responseTime && (
              <div style={{ marginTop: "var(--space-3)", color: "var(--text-muted)", fontSize: "var(--text-sm)" }}>
                ⏱ Thời gian trả lời: {responseTime}
              </div>
            )}
            {!streaming && (
              <MessageActions text={body} onRegenerate={onRegenerate} onFeedback={onFeedback} feedbackSent={feedbackSent} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
