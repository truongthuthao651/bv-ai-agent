import { useLocale } from "./LocaleContext.jsx";

/** Compact VI | EN switch for app headers. */
export function LanguageToggle() {
  const { locale, setLocale, t } = useLocale();

  const btn = (code, active) => ({
    border: "none",
    cursor: "pointer",
    fontFamily: "var(--font-sans)",
    fontSize: "var(--text-2xs)",
    fontWeight: "var(--weight-bold)",
    letterSpacing: "var(--tracking-wide)",
    padding: "4px 8px",
    borderRadius: "var(--radius-sm)",
    background: active ? "var(--accent-subtle)" : "transparent",
    color: active ? "var(--accent)" : "var(--text-muted)",
    transition: "background 150ms, color 150ms",
  });

  return (
    <div
      role="group"
      aria-label={t("lang.label")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-md)",
        padding: 2,
        background: "var(--surface)",
      }}
    >
      <button type="button" className="bv-focus-ring" style={btn("vi", locale === "vi")} onClick={() => setLocale("vi")}>
        {t("lang.vi")}
      </button>
      <button type="button" className="bv-focus-ring" style={btn("en", locale === "en")} onClick={() => setLocale("en")}>
        {t("lang.en")}
      </button>
    </div>
  );
}
