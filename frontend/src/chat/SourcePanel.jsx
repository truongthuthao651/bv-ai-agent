import { Button } from "../components/index.js";

/** Citation detail body — shared by the desktop side panel and mobile modal. */
export function SourcePanelContent({ citation }) {
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
        Mở tài liệu
      </a>
    </>
  );
}

/** Desktop side panel for citation details. On mobile, ChatScreen renders
 * the same content inside a Modal instead — see SourcePanelContent above. */
export function SourcePanel({ citation, onClose }) {
  return (
    <aside style={{ width: "var(--panel-width)", flexShrink: 0, borderLeft: "1px solid var(--border)", background: "var(--surface)", display: "flex", flexDirection: "column", height: "100%", boxSizing: "border-box" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 56, padding: "0 var(--space-5)", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ fontSize: "var(--text-2xs)", fontWeight: "var(--weight-bold)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--tracking-wide)" }}>
          Nguồn {citation.n}
        </div>
        <Button
          variant="ghost"
          onClick={onClose}
          aria-label="Đóng khung nguồn"
          style={{ width: 28, height: 28, padding: 0, fontSize: 15, lineHeight: 1, border: "none" }}
        >
          ✕
        </Button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-5)" }}>
        <SourcePanelContent citation={citation} />
      </div>
    </aside>
  );
}
