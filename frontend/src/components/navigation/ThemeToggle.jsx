import React, { useContext } from "react";
import { LocaleContext } from "../../i18n/LocaleContext.jsx";
import { Icon } from "../icons/Icon.jsx";

/** Matches Button/Input at sm: --control-h-sm, so it lines up in a toolbar row.
 *  `iconOnly` is the 32px square used in both kit headers. */
export function ThemeToggle({ theme, onChange, iconOnly = false }) {
  const localeCtx = useContext(LocaleContext);
  const dark = theme === "dark";
  const [hover, setHover] = React.useState(false);
  const label = dark
    ? localeCtx?.t("theme.toLight") ?? "Chuyển sang sáng"
    : localeCtx?.t("theme.toDark") ?? "Chuyển sang tối";
  const modeLabel = dark
    ? localeCtx?.t("theme.dark") ?? "Tối"
    : localeCtx?.t("theme.light") ?? "Sáng";
  return (
    <button
      onClick={() => onChange(dark ? "light" : "dark")}
      aria-label={label}
      title={label}
      className="bv-focus-ring"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "var(--space-2)",
        height: "var(--control-h-sm)",
        width: iconOnly ? "var(--control-h-sm)" : "auto",
        padding: iconOnly ? 0 : "0 var(--pad-control-x)",
        borderRadius: iconOnly ? "var(--radius-md)" : "var(--radius-pill)",
        border: "1px solid var(--border)",
        background: hover ? "var(--hover)" : "var(--surface)",
        color: "var(--text-secondary)",
        cursor: "pointer",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-xs)",
        fontWeight: "var(--weight-semibold)",
        transition: "background 150ms",
      }}
    >
      <Icon name={dark ? "moon" : "sun"} size={14} aria-hidden />
      {!iconOnly && modeLabel}
    </button>
  );
}
