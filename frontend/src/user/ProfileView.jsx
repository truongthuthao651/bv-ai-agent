import { useEffect, useState } from "react";
import { Badge, Button, Card, Input, ThemeToggle } from "../components/index.js";
import { UserAvatar } from "../components/user/UserAvatar.jsx";
import { AVATAR_SWATCHES, roleLabel } from "./profilePrefs.js";

function Section({ title, hint, children }) {
  return (
    <Card style={{ padding: "var(--pad-card-lg)" }}>
      <div style={{ marginBottom: "var(--space-4)" }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)" }}>{title}</div>
        {hint && (
          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginTop: "var(--space-1)", lineHeight: "var(--leading-normal)" }}>
            {hint}
          </div>
        )}
      </div>
      {children}
    </Card>
  );
}

function ChangePasswordForm({ onChangePassword }) {
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
      await onChangePassword(currentPassword, newPassword);
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
        <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", marginBottom: "var(--space-1)" }}>
          Mật khẩu hiện tại
        </label>
        <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} style={{ width: "100%" }} />
      </div>
      <div>
        <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", marginBottom: "var(--space-1)" }}>
          Mật khẩu mới (ít nhất 8 ký tự)
        </label>
        <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} style={{ width: "100%" }} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <Button onClick={save} disabled={busy}>
          Lưu mật khẩu
        </Button>
        {status.text && <span style={{ fontSize: "var(--text-xs)", color: toneColor }}>{status.text}</span>}
      </div>
    </div>
  );
}

function ThemeChoice({ preference, onChange }) {
  const options = [
    { id: "light", label: "Sáng" },
    { id: "dark", label: "Tối" },
    { id: "system", label: "Theo hệ thống" },
  ];
  return (
    <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
      {options.map((opt) => {
        const active = preference === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onChange(opt.id)}
            style={{
              height: "var(--control-h-sm)",
              padding: "0 var(--pad-control-x)",
              borderRadius: "var(--radius-md)",
              border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
              background: active ? "var(--accent-subtle)" : "var(--surface)",
              color: active ? "var(--accent)" : "var(--text-secondary)",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-xs)",
              fontWeight: "var(--weight-semibold)",
              cursor: "pointer",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

/** Self-service profile — everything the server actually supports (email,
 *  role, password) plus client-side personalization stored in localStorage. */
export function ProfileView({
  me,
  prefs,
  onPrefsChange,
  theme,
  themePreference,
  onThemePreference,
  onChangePassword,
  onLogout,
  onBack,
  conversationCount = 0,
  onClearConversations,
  backLabel = "Quay lại",
  conversations = [],
  activeConversation = null,
  onExportAll,
  onExportActiveMarkdown,
  onExportActiveJson,
}) {
  const [clearConfirm, setClearConfirm] = useState(false);
  const [nameDraft, setNameDraft] = useState(prefs.displayName);
  const [nameStatus, setNameStatus] = useState({ text: "", tone: "" });
  const [avatarStatus, setAvatarStatus] = useState("");

  useEffect(() => {
    setNameDraft(prefs.displayName);
  }, [prefs.displayName]);

  const nameDirty = nameDraft.trim() !== prefs.displayName;

  useEffect(() => {
    if (!nameDirty) return;
    function onBeforeUnload(e) {
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [nameDirty]);

  function handleBack() {
    if (nameDirty && !window.confirm("Tên hiển thị chưa được lưu. Bỏ qua thay đổi?")) return;
    onBack();
  }

  function saveDisplayName() {
    const next = nameDraft.trim();
    if (!next) {
      setNameStatus({ text: "Tên không được để trống.", tone: "bad" });
      return;
    }
    onPrefsChange({ displayName: next });
    setNameStatus({ text: "Đã lưu.", tone: "ok" });
  }

  if (!me?.email) {
    return (
      <div style={{ padding: "var(--space-8)", textAlign: "center", color: "var(--text-secondary)" }}>
        Không thể tải thông tin tài khoản.
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "var(--space-8) var(--space-5) var(--space-16)",
        boxSizing: "border-box",
      }}
    >
      <div style={{ maxWidth: 640, margin: "0 auto", display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <Button variant="secondary" onClick={handleBack}>
            ← {backLabel}
          </Button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
          <UserAvatar email={me.email} swatchId={prefs.avatarSwatch} size={56} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: "var(--text-xl)", fontWeight: "var(--weight-bold)", color: "var(--text-primary)", letterSpacing: "var(--tracking-tight)" }}>
              {prefs.displayName}
            </div>
            <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginTop: "var(--space-1)" }}>{me.email}</div>
            <div style={{ marginTop: "var(--space-2)" }}>
              <Badge label={roleLabel(me.role)} status="neutral" />
            </div>
          </div>
        </div>

        <Section title="Cá nhân hoá" hint="Tên hiển thị và màu avatar được lưu trên máy chủ — đồng bộ giữa các thiết bị. Giao diện sáng/tối vẫn theo từng trình duyệt.">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <div>
              <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", marginBottom: "var(--space-1)" }}>
                Tên hiển thị
              </label>
              <Input
                value={nameDraft}
                onChange={(e) => {
                  setNameDraft(e.target.value);
                  setNameStatus({ text: "", tone: "" });
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.nativeEvent.isComposing && nameDirty) {
                    e.preventDefault();
                    saveDisplayName();
                  }
                }}
                placeholder="Tên bạn muốn hiển thị"
                style={{ width: "100%" }}
              />
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginTop: "var(--space-3)", flexWrap: "wrap" }}>
                <Button onClick={saveDisplayName} disabled={!nameDirty}>
                  Lưu tên
                </Button>
                {nameStatus.text && (
                  <span
                    style={{
                      fontSize: "var(--text-xs)",
                      color: { ok: "var(--success)", bad: "var(--danger)", "": "var(--text-secondary)" }[nameStatus.tone],
                    }}
                  >
                    {nameStatus.text}
                  </span>
                )}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", marginBottom: "var(--space-2)" }}>
                Màu avatar
              </div>
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                {AVATAR_SWATCHES.map((swatch) => (
                  <button
                    key={swatch.id}
                    type="button"
                    aria-label={`Màu avatar ${swatch.id}`}
                    onClick={() => {
                      onPrefsChange({ avatarSwatch: swatch.id });
                      setAvatarStatus("Đã lưu.");
                      setTimeout(() => setAvatarStatus(""), 2000);
                    }}
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: "50%",
                      border: prefs.avatarSwatch === swatch.id ? "2px solid var(--accent)" : "1px solid var(--border)",
                      background: swatch.bg,
                      color: swatch.color,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "var(--text-xs)",
                      fontWeight: "var(--weight-bold)",
                      cursor: "pointer",
                      fontFamily: "var(--font-sans)",
                    }}
                  >
                    {me.email[0].toUpperCase()}
                  </button>
                ))}
              </div>
              {avatarStatus && (
                <span style={{ fontSize: "var(--text-xs)", color: "var(--success)", marginTop: "var(--space-2)", display: "block" }}>
                  {avatarStatus}
                </span>
              )}
            </div>
          </div>
        </Section>

        <Section title="Giao diện" hint="Chọn chế độ sáng/tối hoặc theo cài đặt hệ thống.">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-4)", flexWrap: "wrap" }}>
            <ThemeChoice preference={themePreference} onChange={onThemePreference} />
            <ThemeToggle theme={theme} onChange={(next) => onThemePreference(next)} iconOnly />
          </div>
        </Section>

        <Section title="Bảo mật" hint="Đổi mật khẩu cho tài khoản đang đăng nhập.">
          <ChangePasswordForm onChangePassword={onChangePassword} />
        </Section>

        {onClearConversations != null && (
          <Section
            title="Dữ liệu trò chuyện"
            hint="Cuộc trò chuyện được lưu trên máy chủ, riêng từng tài khoản — quản trị viên không xem được nội dung chat của nhân viên."
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                {conversationCount === 0
                  ? "Chưa có cuộc trò chuyện nào trong tab này."
                  : `${conversationCount} cuộc trò chuyện trong tab này.`}
              </div>
              {conversationCount > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
                  {activeConversation && onExportActiveMarkdown && (
                    <Button variant="secondary" onClick={onExportActiveMarkdown}>
                      Xuất cuộc trò chuyện hiện tại (Markdown)
                    </Button>
                  )}
                  {activeConversation && onExportActiveJson && (
                    <Button variant="secondary" onClick={onExportActiveJson}>
                      Xuất cuộc trò chuyện hiện tại (JSON)
                    </Button>
                  )}
                  {onExportAll && conversations.length > 0 && (
                    <Button variant="secondary" onClick={onExportAll}>
                      Xuất tất cả ({conversations.length}) — JSON
                    </Button>
                  )}
                </div>
              )}
              {conversationCount > 0 && (
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
                  {!clearConfirm ? (
                    <Button variant="secondary" onClick={() => setClearConfirm(true)}>
                      Xóa tất cả cuộc trò chuyện
                    </Button>
                  ) : (
                    <>
                      <span style={{ fontSize: "var(--text-xs)", color: "var(--danger)" }}>Không thể hoàn tác.</span>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          onClearConversations();
                          setClearConfirm(false);
                        }}
                      >
                        Xác nhận xóa
                      </Button>
                      <Button variant="ghost" onClick={() => setClearConfirm(false)}>
                        Huỷ
                      </Button>
                    </>
                  )}
                </div>
              )}
            </div>
          </Section>
        )}

        <Section title="Phiên đăng nhập">
          <Button
            variant="secondary"
            onClick={() => onLogout().then(() => (window.location.href = "/login"))}
          >
            Đăng xuất
          </Button>
        </Section>
      </div>
    </div>
  );
}
