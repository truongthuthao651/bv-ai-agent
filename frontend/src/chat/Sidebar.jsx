import { useState } from "react";
import { Button, Input, Modal, ThemeToggle } from "../components/index.js";
import { changePassword, logout } from "./api.js";

/** P2-J6 (audit/REPORT.md) — the minimum viable self-service surface: change
 * the signed-in account's own password. Exactly two fields, matching the
 * audit's own "minimum viable" framing rather than a full profile page. */
function ChangePasswordModal({ onClose }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [status, setStatus] = useState({ text: "", tone: "" });
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!currentPassword || !newPassword) {
      setStatus({ text: "Vui lòng nhập đủ cả hai mật khẩu.", tone: "bad" });
      return;
    }
    setBusy(true);
    setStatus({ text: "", tone: "" });
    try {
      await changePassword(currentPassword, newPassword);
      setStatus({ text: "Đã đổi mật khẩu.", tone: "ok" });
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setStatus({ text: err.message, tone: "bad" });
    } finally {
      setBusy(false);
    }
  }

  const toneColor = { ok: "var(--success)", bad: "var(--danger)", "": "var(--text-secondary)" }[status.tone];

  return (
    <Modal
      open
      title="Đổi mật khẩu"
      hint="Đổi mật khẩu cho tài khoản đang đăng nhập."
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Đóng
          </Button>
          <Button onClick={save} disabled={busy}>
            Lưu
          </Button>
        </>
      }
    >
      <div
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (!busy) save();
          }
        }}
        style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}
      >
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>Mật khẩu hiện tại</label>
          <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} style={{ width: "100%" }} />
        </div>
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>Mật khẩu mới (ít nhất 8 ký tự)</label>
          <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} style={{ width: "100%" }} />
        </div>
        {status.text && <div style={{ fontSize: "var(--text-xs)", color: toneColor }}>{status.text}</div>}
      </div>
    </Modal>
  );
}

/** Ported from ui_kits/chatbot/ChatParts.jsx's Sidebar, with the fabricated
 * "Pinned/Today/Yesterday" thread list and the dead "Search chats ⌘K" hint
 * dropped — there is no conversation persistence yet (Phase 4 gap list), so
 * a thread list would either be empty forever or lie. The bottom user block
 * shows the real signed-in account instead of the kit's "Nguyễn Vân". */
export function Sidebar({ me, theme, onTheme, onClose, onNewChat }) {
  const [showProfile, setShowProfile] = useState(false);
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
            <button
              onClick={() => setShowProfile(true)}
              title="Đổi mật khẩu"
              aria-label="Tài khoản: đổi mật khẩu"
              style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flex: 1, minWidth: 0, border: "none", background: "transparent", cursor: "pointer", padding: 0, textAlign: "left" }}
            >
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
            </button>
            <button
              onClick={() => logout().then(() => (window.location.href = "/login"))}
              title="Đăng xuất"
              aria-label="Đăng xuất"
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
      {showProfile && <ChangePasswordModal onClose={() => setShowProfile(false)} />}
    </aside>
  );
}
