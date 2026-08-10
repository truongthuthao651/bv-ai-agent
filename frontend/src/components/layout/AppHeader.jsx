import { BrandGlobe } from "../../brand/BrandGlobe.jsx";
import { LanguageToggle } from "../../i18n/LanguageToggle.jsx";
import { ThemeToggle } from "../navigation/ThemeToggle.jsx";

/** Shared top bar for chat and admin — logo, title, language + theme controls. */
export function AppHeader({ title, menu, expand, theme, onTheme }) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-3)",
        height: 64,
        flexShrink: 0,
        padding: "0 var(--space-4) 0 var(--space-5)",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg)",
      }}
    >
      {menu}
      {expand}
      <BrandGlobe size={32} alt="" />
      <div
        style={{
          minWidth: 0,
          flex: 1,
          fontSize: "var(--text-md)",
          fontWeight: "var(--weight-semibold)",
          color: "var(--text-primary)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          lineHeight: "var(--leading-snug)",
        }}
      >
        {title}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexShrink: 0 }}>
        <LanguageToggle />
        <ThemeToggle theme={theme} onChange={onTheme} iconOnly />
      </div>
    </header>
  );
}

/** Sidebar rail title block with globe + product name. */
export function SidebarBrand({ title, subtitle }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", minWidth: 0 }}>
      <BrandGlobe size={36} alt="" />
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "var(--text-md)",
            fontWeight: "var(--weight-bold)",
            color: "var(--text-primary)",
            lineHeight: "var(--leading-snug)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 2 }}>{subtitle}</div>
        )}
      </div>
    </div>
  );
}
