import { useLocale } from "./LocaleContext.jsx";

/** Compact VI | EN switch for app headers and dark public pages. */
export function LanguageToggle({ variant = "light" }) {
  const { locale, setLocale, t } = useLocale();
  const onDark = variant === "dark";

  const btn = (active) => ({
    border: "none",
    cursor: "pointer",
    fontFamily: "var(--font-sans)",
    fontSize: "var(--text-2xs)",
    fontWeight: "var(--weight-bold)",
    letterSpacing: "var(--tracking-wide)",
    padding: "4px 8px",
    borderRadius: "var(--radius-sm)",
    background: active
      ? onDark
        ? "rgba(224, 162, 8, 0.22)"
        : "var(--accent-subtle)"
      : "transparent",
    color: active
      ? onDark
        ? "var(--brand-gold-light)"
        : "var(--accent)"
      : onDark
        ? "rgba(255, 255, 255, 0.55)"
        : "var(--text-muted)",
    transition: "background 150ms, color 150ms",
  });

  return (
    <div
      role="group"
      aria-label={t("lang.label")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        border: onDark ? "1px solid rgba(255, 255, 255, 0.18)" : "1px solid var(--border)",
        borderRadius: "var(--radius-md)",
        padding: 2,
        background: onDark ? "rgba(255, 255, 255, 0.08)" : "var(--surface)",
      }}
    >
      <button type="button" className="bv-focus-ring" style={btn(locale === "vi")} onClick={() => setLocale("vi")}>
        {t("lang.vi")}
      </button>
      <button type="button" className="bv-focus-ring" style={btn(locale === "en")} onClick={() => setLocale("en")}>
        {t("lang.en")}
      </button>
    </div>
  );
}
