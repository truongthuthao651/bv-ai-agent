import { useEffect, useState } from "react";
import { Badge, Button, Input, Modal, ThemeToggle } from "../components/index.js";
import { useTheme } from "../theme/useTheme.js";
import { changePassword, fetchHealth, fetchMe, logout } from "./api.js";
import { OverviewView } from "./OverviewView.jsx";
import { DocumentsView } from "./DocumentsView.jsx";
import { UsersView } from "./UsersView.jsx";

/** P2-J6 (audit/REPORT.md) — the minimum viable self-service surface: change
 * the signed-in account's own password. Exactly two fields, matching the
 * audit's own "minimum viable" framing rather than a full profile page.
 * Identical to chat/Sidebar.jsx's copy of the same modal — kept as two small
 * local components rather than a shared file, consistent with this
 * codebase's existing chat/admin api.js duplication (see that file's own
 * comment: separate on purpose so the two bundles stay independent). */
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

/* Grouped exactly as the kit has it (Monitor / Content / Configure —
 * REDESIGN_PROMPT.md §8), so nobody has to hunt for a moved item once a
 * section ships. Only "Tổng quan" and "Tài liệu" are real; every other item
 * renders an honest placeholder instead of the kit's fabricated pages. */
const NAV_GROUPS = [
  {
    title: "Theo dõi",
    items: [
      { key: "overview", label: "Tổng quan" },
      { key: "evaluation", label: "Đánh giá chất lượng" },
      { key: "logs", label: "Nhật ký" },
    ],
  },
  {
    title: "Nội dung",
    items: [
      { key: "documents", label: "Tài liệu" },
      { key: "users", label: "Người dùng" },
    ],
  },
  {
    title: "Cấu hình",
    items: [
      { key: "models", label: "Mô hình" },
      { key: "settings", label: "Thiết lập" },
    ],
  },
];

const PLACEHOLDER_COPY = {
  evaluation: "Chưa được xây dựng trong bản này — số liệu đánh giá chất lượng (RAGAS) hiện chỉ chạy offline qua eval/run_ragas.py, chưa có màn hình riêng.",
  logs: "Chưa được xây dựng trong bản này.",
  models: "Chưa được xây dựng trong bản này — mô hình đang dùng được đặt qua biến CHAT_MODEL trong .env.",
  settings: "Ứng dụng không có bảng cấu hình qua giao diện — mọi tham số (mô hình, ngưỡng, đường dẫn) được đặt trong tệp .env trên máy chủ và áp dụng khi khởi động lại dịch vụ.",
};

function Placeholder({ navKey, label }) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "var(--space-20) var(--space-5)",
        border: "1px dashed var(--border-strong)",
        borderRadius: "var(--radius-xl)",
      }}
    >
      <div
        style={{
          fontSize: "var(--text-lg)",
          fontWeight: "var(--weight-semibold)",
          color: "var(--text-primary)",
          marginBottom: "var(--space-2)",
          letterSpacing: "var(--tracking-tight)",
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", maxWidth: 480, margin: "0 auto" }}>
        {PLACEHOLDER_COPY[navKey] || "Chưa được xây dựng trong bản này."}
      </div>
    </div>
  );
}

const NAV_KEYS = new Set(NAV_GROUPS.flatMap((g) => g.items).map((it) => it.key));

function navFromHash() {
  const key = window.location.hash.slice(1);
  return NAV_KEYS.has(key) ? key : "overview";
}

// F3-4 (audit/REPORT.md): the rail was a fixed var(--rail-width) with no
// responsive handling at all — unusable below ~900px (KPI labels truncated
// to "Số...", the rail alone ate 70% of a phone screen). Same 640px
// threshold and slide-over-drawer pattern already proven in
// chat/ChatScreen.jsx's useIsMobile/Sidebar — ported here rather than
// invented fresh.
function useIsMobile() {
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 640px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    const onChange = () => setMobile(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return mobile;
}

export function AdminShell() {
  const [theme, setTheme] = useTheme();
  const [active, setActive] = useState(navFromHash);
  const [hoverNav, setHoverNav] = useState(null);
  const [health, setHealth] = useState(null);
  const [me, setMe] = useState(null);
  const [railOpen, setRailOpen] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const mobile = useIsMobile();

  useEffect(() => {
    fetchMe()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  // Deep-linkable tabs (#documents, #overview, ...) so a bookmark or refresh
  // lands back on the right screen instead of always resetting to Overview.
  useEffect(() => {
    const onHashChange = () => setActive(navFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function selectNav(key) {
    window.location.hash = key;
    setActive(key);
    setRailOpen(false);
  }

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const data = await fetchHealth();
        if (!cancelled) setHealth(data);
      } catch {
        if (!cancelled) setHealth(null);
      }
    }
    poll();
    const id = setInterval(poll, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const navBtn = (key) => ({
    display: "flex",
    alignItems: "center",
    width: "100%",
    textAlign: "left",
    border: "none",
    background: active === key ? "var(--accent-subtle)" : hoverNav === key ? "var(--hover)" : "transparent",
    color: active === key ? "var(--accent)" : "var(--text-secondary)",
    fontWeight: active === key ? "var(--weight-semibold)" : "var(--weight-medium)",
    fontFamily: "var(--font-sans)",
    fontSize: "var(--text-sm)",
    padding: "var(--space-2) var(--space-3)",
    borderRadius: "var(--radius-md)",
    cursor: "pointer",
    transition: "background 150ms cubic-bezier(.2,.8,.2,1), color 150ms",
  });

  const ollamaStatus = health?.services?.ollama?.status;
  const qdrantStatus = health?.services?.qdrant?.status;

  async function handleLogout() {
    await logout();
    window.location.href = "/login";
  }

  // Rendered both as the static desktop rail and, unchanged, inside the
  // mobile slide-over drawer below — a closure variable rather than a
  // separate component so it keeps direct access to all the state/handlers
  // above without threading eight props through.
  const railContent = (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)", padding: "var(--space-5) var(--space-4) var(--space-6)" }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-bold)", color: "var(--text-primary)" }}>
          Trợ lý AI Bảo Việt Life
        </div>
        <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>Quản trị tài liệu</div>
      </div>

      <nav style={{ flex: 1, overflowY: "auto", padding: "0 var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-6)", minHeight: 0 }}>
        {NAV_GROUPS.map((g) => (
          <div key={g.title} style={{ display: "flex", flexDirection: "column", gap: "var(--space-half)" }}>
            <div
              style={{
                fontSize: "var(--text-2xs)",
                fontWeight: "var(--weight-bold)",
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "var(--tracking-wide)",
                padding: "0 var(--space-3)",
                marginBottom: "var(--space-1)",
              }}
            >
              {g.title}
            </div>
            {g.items.map((it) => (
              <button
                key={it.key}
                onClick={() => selectNav(it.key)}
                onMouseEnter={() => setHoverNav(it.key)}
                onMouseLeave={() => setHoverNav(null)}
                style={navBtn(it.key)}
              >
                {it.label}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div style={{ borderTop: "1px solid var(--border)", padding: "var(--space-3) var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
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
                <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>{me.role === "admin" ? "Quản trị viên" : "Nhân viên"}</div>
              </div>
            </button>
            <button
              onClick={handleLogout}
              title="Đăng xuất"
              aria-label="Đăng xuất"
              style={{ border: "none", background: "transparent", color: "var(--text-muted)", cursor: "pointer", fontSize: 15, padding: 4, flexShrink: 0 }}
            >
              ⏻
            </button>
          </div>
        )}
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
          <Badge label={`Ollama: ${ollamaStatus === "up" ? "Hoạt động" : "Ngừng"}`} status={ollamaStatus === "up" ? "ok" : "bad"} />
          <Badge label={`Qdrant: ${qdrantStatus === "up" ? "Hoạt động" : "Ngừng"}`} status={qdrantStatus === "up" ? "ok" : "bad"} />
        </div>
        <a
          href="/chat/"
          style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--accent)", textDecoration: "none" }}
        >
          Mở giao diện trò chuyện ↗
        </a>
      </div>
    </>
  );

  return (
    <div
      data-theme={theme}
      style={{ height: "100vh", background: "var(--bg)", fontFamily: "var(--font-sans)", display: "flex", overflow: "hidden" }}
    >
      {!mobile && (
        <aside
          style={{
            width: "var(--rail-width)",
            flexShrink: 0,
            borderRight: "1px solid var(--border)",
            background: "var(--surface)",
            display: "flex",
            flexDirection: "column",
            boxSizing: "border-box",
          }}
        >
          {railContent}
        </aside>
      )}
      {mobile && railOpen && (
        <div
          onClick={() => setRailOpen(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(6,18,30,.5)", backdropFilter: "blur(2px)", zIndex: 20 }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: "var(--rail-width)",
              maxWidth: "85vw",
              background: "var(--surface)",
              display: "flex",
              flexDirection: "column",
              boxSizing: "border-box",
              boxShadow: "var(--shadow-lg)",
            }}
          >
            {railContent}
          </div>
        </div>
      )}

      <main style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <header
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-4)",
            height: 56,
            flexShrink: 0,
            padding: mobile ? "0 var(--space-4)" : "0 var(--pad-page)",
            borderBottom: "1px solid var(--border)",
            background: "var(--bg)",
          }}
        >
          {mobile && (
            <button
              onClick={() => setRailOpen(true)}
              aria-label="Mở menu"
              style={{ border: "none", background: "transparent", fontSize: 17, cursor: "pointer", color: "var(--text-primary)", padding: 0, width: 32, height: 32, flexShrink: 0 }}
            >
              ☰
            </button>
          )}
          <div style={{ minWidth: 0, fontSize: "var(--text-sm)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {NAV_GROUPS.flatMap((g) => g.items).find((it) => it.key === active)?.label}
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <ThemeToggle theme={theme} onChange={setTheme} iconOnly />
          </div>
        </header>

        <div style={{ flex: 1, overflowY: "auto", padding: "var(--pad-page) var(--pad-page) var(--space-16)" }}>
          <div style={{ maxWidth: 1400, margin: "0 auto" }}>
            {active === "overview" && <OverviewView />}
            {active === "documents" && <DocumentsView canManage={me?.role === "admin"} />}
            {active === "users" && <UsersView />}
            {!["overview", "documents", "users"].includes(active) && (
              <Placeholder navKey={active} label={NAV_GROUPS.flatMap((g) => g.items).find((it) => it.key === active)?.label} />
            )}
          </div>
        </div>
      </main>
      {showProfile && <ChangePasswordModal onClose={() => setShowProfile(false)} />}
    </div>
  );
}
