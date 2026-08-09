import { useEffect, useState } from "react";
import { Badge, Button, Card, Icon, Input, ThemeToggle } from "../components/index.js";
import { UserAvatar } from "../components/user/UserAvatar.jsx";
import { localizedRoleLabel } from "../i18n/catalog.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { AVATAR_SWATCHES } from "./profilePrefs.js";

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
  const { t } = useLocale();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [status, setStatus] = useState({ text: "", tone: "" });
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!currentPassword || !newPassword) {
      setStatus({ text: t("profile.passwordRequired"), tone: "bad" });
      return;
    }
    setBusy(true);
    setStatus({ text: "", tone: "" });
    try {
      await onChangePassword(currentPassword, newPassword);
      setStatus({ text: t("profile.passwordChanged"), tone: "ok" });
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
          {t("profile.currentPassword")}
        </label>
        <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} style={{ width: "100%" }} />
      </div>
      <div>
        <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", marginBottom: "var(--space-1)" }}>
          {t("profile.newPassword")}
        </label>
        <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} style={{ width: "100%" }} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <Button onClick={save} disabled={busy}>
          {t("profile.savePassword")}
        </Button>
        {status.text && <span style={{ fontSize: "var(--text-xs)", color: toneColor }}>{status.text}</span>}
      </div>
    </div>
  );
}

function ThemeChoice({ preference, onChange }) {
  const { t } = useLocale();
  const options = [
    { id: "light", label: t("theme.light") },
    { id: "dark", label: t("theme.dark") },
    { id: "system", label: t("theme.system") },
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
  const { t } = useLocale();
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
    if (nameDirty && !window.confirm(t("profile.unsavedConfirm"))) return;
    onBack();
  }

  function saveDisplayName() {
    const next = nameDraft.trim();
    if (!next) {
      setNameStatus({ text: t("profile.nameRequired"), tone: "bad" });
      return;
    }
    onPrefsChange({ displayName: next });
    setNameStatus({ text: t("profile.saved"), tone: "ok" });
  }

  if (!me?.email) {
    return (
      <div style={{ padding: "var(--space-8)", textAlign: "center", color: "var(--text-secondary)" }}>
        {t("profile.loadError")}
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
          <Button variant="secondary" onClick={handleBack} style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)" }}>
            <Icon name="arrow-left" size={14} /> {backLabel}
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
              <Badge label={localizedRoleLabel(me.role, t)} status="neutral" />
            </div>
          </div>
        </div>

        <Section title={t("profile.personalization")} hint={t("profile.personalizationHint")}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <div>
              <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", marginBottom: "var(--space-1)" }}>
                {t("profile.displayName")}
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
                placeholder={t("profile.displayNamePlaceholder")}
                style={{ width: "100%" }}
              />
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginTop: "var(--space-3)", flexWrap: "wrap" }}>
                <Button onClick={saveDisplayName} disabled={!nameDirty}>
                  {t("profile.saveName")}
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
                {t("profile.avatarColor")}
              </div>
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                {AVATAR_SWATCHES.map((swatch) => (
                  <button
                    key={swatch.id}
                    type="button"
                    aria-label={t("profile.avatarColorLabel", { id: swatch.id })}
                    onClick={() => {
                      onPrefsChange({ avatarSwatch: swatch.id });
                      setAvatarStatus(t("profile.saved"));
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

        <Section title={t("profile.appearance")} hint={t("profile.appearanceHint")}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-4)", flexWrap: "wrap" }}>
            <ThemeChoice preference={themePreference} onChange={onThemePreference} />
            <ThemeToggle theme={theme} onChange={(next) => onThemePreference(next)} iconOnly />
          </div>
        </Section>

        <Section title={t("profile.security")} hint={t("profile.securityHint")}>
          <ChangePasswordForm onChangePassword={onChangePassword} />
        </Section>

        {onClearConversations != null && (
          <Section
            title={t("profile.conversations")}
            hint={t("profile.conversationsHint")}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                {conversationCount === 0
                  ? t("profile.noConversations")
                  : t("profile.conversationCount", { n: conversationCount })}
              </div>
              {conversationCount > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
                  {activeConversation && onExportActiveMarkdown && (
                    <Button variant="secondary" onClick={onExportActiveMarkdown}>
                      {t("profile.exportMarkdown")}
                    </Button>
                  )}
                  {activeConversation && onExportActiveJson && (
                    <Button variant="secondary" onClick={onExportActiveJson}>
                      {t("profile.exportJson")}
                    </Button>
                  )}
                  {onExportAll && conversations.length > 0 && (
                    <Button variant="secondary" onClick={onExportAll}>
                      {t("profile.exportAll", { n: conversations.length })}
                    </Button>
                  )}
                </div>
              )}
              {conversationCount > 0 && (
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
                  {!clearConfirm ? (
                    <Button variant="secondary" onClick={() => setClearConfirm(true)}>
                      {t("profile.deleteAll")}
                    </Button>
                  ) : (
                    <>
                      <span style={{ fontSize: "var(--text-xs)", color: "var(--danger)" }}>{t("profile.deleteIrreversible")}</span>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          onClearConversations();
                          setClearConfirm(false);
                        }}
                      >
                        {t("profile.confirmDelete")}
                      </Button>
                      <Button variant="ghost" onClick={() => setClearConfirm(false)}>
                        {t("common.cancel")}
                      </Button>
                    </>
                  )}
                </div>
              )}
            </div>
          </Section>
        )}

        <Section title={t("profile.session")}>
          <Button
            variant="secondary"
            onClick={() => onLogout().then(() => (window.location.href = "/login"))}
          >
            {t("profile.logout")}
          </Button>
        </Section>
      </div>
    </div>
  );
}
