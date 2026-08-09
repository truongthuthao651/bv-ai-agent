import { useEffect, useState } from "react";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { fetchPromptSuggestions } from "./api.js";

function SuggestionButton({ suggestion, onPick }) {
  const [hover, setHover] = useState(false);
  const title = suggestion.title?.[1] || suggestion.content;
  return (
    <button
      onClick={() => onPick(suggestion.content)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="bv-focus-ring"
      style={{
        textAlign: "left",
        border: "1px solid " + (hover ? "var(--border-strong)" : "var(--border)"),
        background: hover ? "var(--hover)" : "var(--surface)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-3) var(--space-4)",
        cursor: "pointer",
        fontFamily: "var(--font-sans)",
        boxShadow: hover ? "var(--shadow-md)" : "var(--shadow-sm)",
        transition: "background 150ms, border-color 150ms, box-shadow 150ms",
      }}
    >
      {suggestion.title?.[0] && (
        <div style={{ fontSize: "var(--text-2xs)", fontWeight: "var(--weight-bold)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--tracking-wide)", marginBottom: "var(--space-1)" }}>
          {suggestion.title[0]}
        </div>
      )}
      <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)", color: "var(--text-primary)", lineHeight: "var(--leading-snug)" }}>{title}</div>
    </button>
  );
}

/** Chat empty state: flat grid of prompt suggestions from GET /prompt-suggestions. */
export function EmptyState({ me, displayName, onPick }) {
  const { locale, t } = useLocale();
  const [suggestions, setSuggestions] = useState([]);

  useEffect(() => {
    fetchPromptSuggestions(locale)
      .then(setSuggestions)
      .catch(() => setSuggestions([]));
  }, [locale]);

  const nameSuffix = displayName
    ? `, ${displayName}`
    : me?.email
      ? `, ${me.email.split("@")[0]}`
      : "";

  return (
    <div style={{ margin: "auto", width: "100%", maxWidth: "var(--content-max)", padding: "var(--space-12) var(--space-8)", boxSizing: "border-box" }}>
      <div style={{ fontSize: "var(--text-3xl)", fontWeight: "var(--weight-heavy)", letterSpacing: "var(--tracking-tight)", color: "var(--text-primary)", lineHeight: "var(--leading-tight)", marginBottom: "var(--space-8)" }}>
        {t("chat.greeting")}
        {nameSuffix}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "var(--gap-card)" }}>
        {suggestions.map((s, i) => (
          <SuggestionButton key={i} suggestion={s} onPick={onPick} />
        ))}
      </div>
    </div>
  );
}
