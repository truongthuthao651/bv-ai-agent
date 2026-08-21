import { IconButton } from "../components/index.js";
import { useLocale } from "../i18n/LocaleContext.jsx";

/** Citation detail body — shared by the desktop side panel and mobile modal. */
export function SourcePanelContent({ citation }) {
  const { t } = useLocale();
  return (
    <>
      <div style={{ fontSize: "var(--text-md)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", lineHeight: "var(--leading-snug)", letterSpacing: "var(--tracking-tight)" }}>
        {citation.title}
      </div>
      {citation.meta && <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: "var(--space-1)" }}>{citation.meta}</div>}

      <a
        href={citation.url}
        target="_blank"
        rel="noopener"
        style={{
          display: "block",
          textAlign: "center",
          marginTop: "var(--space-5)",
          height: "var(--control-h-sm)",
          lineHeight: "var(--control-h-sm)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)",
          fontSize: "var(--text-xs)",
          fontWeight: "var(--weight-semibold)",
          color: "var(--text-secondary)",
          textDecoration: "none",
        }}
      >
        {t("chat.openCitation")}
      </a>
    </>
  );
}

/** Desktop side panel for citation details. On mobile, ChatScreen renders
 * the same content inside a Modal instead — see SourcePanelContent above. */
export function SourcePanel({ citation, onClose }) {
  const { t } = useLocale();
  return (
    <aside style={{ width: "var(--panel-width)", flexShrink: 0, borderLeft: "1px solid var(--border)", background: "var(--surface)", display: "flex", flexDirection: "column", height: "100%", boxSizing: "border-box" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 56, padding: "0 var(--space-5)", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ fontSize: "var(--text-2xs)", fontWeight: "var(--weight-bold)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--tracking-wide)" }}>
          {t("chat.sourceN", { n: citation.n })}
        </div>
        <IconButton icon="close" label={t("chat.closeSource")} onClick={onClose} size={28} iconSize={16} />
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-5)" }}>
        <SourcePanelContent citation={citation} />
      </div>
    </aside>
  );
}
