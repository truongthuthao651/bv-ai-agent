import { ThemeToggle } from "../components/index.js";
import { logout } from "./api.js";

/** Ported from ui_kits/chatbot/ChatParts.jsx's Sidebar, with the fabricated
 * "Pinned/Today/Yesterday" thread list and the dead "Search chats ⌘K" hint
 * dropped — there is no conversation persistence yet (Phase 4 gap list), so
 * a thread list would either be empty forever or lie. The bottom user block
 * shows the real signed-in account instead of the kit's "Nguyễn Vân". */
export function Sidebar({ me, theme, onTheme, onClose, onNewChat }) {
  return (
    <aside
      style={{
        width: "var(--rail-width)",
        flexShrink: 0,
        borderRight: "1px solid var(--border)",
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "var(--space-5) var(--space-4) var(--space-4)" }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-bold)", color: "var(--text-primary)" }}>Trợ lý AI Bảo Việt Life</div>
        {onClose && (
          <button onClick={onClose} aria-label="Đóng menu" style={{ border: "none", background: "transparent", color: "var(--text-muted)", fontSize: 16, cursor: "pointer" }}>
            ✕
          </button>
        )}
      </div>

      <div style={{ padding: "0 var(--space-4)" }}>
        <button
          onClick={onNewChat}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "var(--space-2)",
            width: "100%",
            height: "var(--control-h-md)",
            border: "none",
            background: "var(--accent)",
            color: "var(--text-on-accent)",
            fontFamily: "var(--font-sans)",
            fontWeight: "var(--weight-semibold)",
            fontSize: "var(--text-sm)",
            borderRadius: "var(--radius-md)",
            cursor: "pointer",
          }}
        >
          <span style={{ fontSize: 15, lineHeight: 1 }}>+</span> Cuộc trò chuyện mới
        </button>
      </div>

      <div style={{ flex: 1 }} />

      <div style={{ borderTop: "1px solid var(--border)", padding: "var(--space-3) var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        <div style={{ display: "flex", justifyContent: "center" }}>
          <ThemeToggle theme={theme} onChange={onTheme} />
        </div>
        {me?.email && (
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: "50%",
                background: "var(--brand-navy)",
                color: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "var(--text-xs)",
                fontWeight: "var(--weight-bold)",
                flexShrink: 0,
              }}
            >
              {me.email[0].toUpperCase()}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {me.email}
              </div>
            </div>
            <button
              onClick={() => logout().then(() => (window.location.href = "/login"))}
              title="Đăng xuất"
              style={{ border: "none", background: "transparent", color: "var(--text-muted)", cursor: "pointer", fontSize: 15, padding: 4, flexShrink: 0 }}
            >
              ⏻
            </button>
          </div>
        )}
        {me?.role === "admin" && (
          <a href="/admin/" style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--accent)", textDecoration: "none" }}>
            Mở trang quản trị ↗
          </a>
        )}
      </div>
    </aside>
  );
}
