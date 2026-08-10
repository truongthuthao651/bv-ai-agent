import { useEffect, useMemo, useRef, useState } from "react";
import { Icon, IconButton, Input, RailCollapseButton, SidebarBrand } from "../components/index.js";
import { localizedGroupConversationsByDate, localizedConversationLabel, localizedRoleLabel } from "../i18n/catalog.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { UserAvatar } from "../components/user/UserAvatar.jsx";
import { logout } from "./api.js";
import { deriveTitle } from "./conversations.js";

function ConversationItem({ conv, label, active, streaming, onSelect, onRename, onDelete }) {
  const { t } = useLocale();
  const [hover, setHover] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);
  const [confirmDelete, setConfirmDelete] = useState(false);

  function commitRename() {
    const next = draft.trim();
    if (next && next !== label) onRename(conv.id, next);
    setEditing(false);
  }

  if (editing) {
    return (
      <div style={{ padding: "var(--space-1) var(--space-2)" }}>
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") setEditing(false);
          }}
          onBlur={commitRename}
          style={{ width: "100%", fontSize: "var(--text-sm)" }}
        />
      </div>
    );
  }

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => {
        setHover(false);
        setConfirmDelete(false);
      }}
      style={{ display: "flex", alignItems: "center", gap: "var(--space-1)", minWidth: 0 }}
    >
      <button
        type="button"
        onClick={() => onSelect(conv.id)}
        style={{
          display: "flex",
          alignItems: "center",
          flex: 1,
          minWidth: 0,
          textAlign: "left",
          border: "none",
          background: active ? "var(--active)" : hover ? "var(--hover)" : "transparent",
          color: active ? "var(--text-primary)" : "var(--text-secondary)",
          padding: "var(--space-2) var(--space-3)",
          borderRadius: "var(--radius-md)",
          fontSize: "var(--text-sm)",
          fontWeight: active ? "var(--weight-semibold)" : "var(--weight-regular)",
          fontFamily: "var(--font-sans)",
          cursor: "pointer",
          transition: "background 150ms",
          overflow: "hidden",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{label}</span>
        {streaming && (
          <span
            title={t("chat.streaming")}
            aria-label={t("chat.streaming")}
            style={{
              flexShrink: 0,
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "var(--accent)",
              animation: "bv-sidebar-stream-pulse 1.2s ease-in-out infinite",
            }}
          />
        )}
      </button>
      {(hover || confirmDelete) && (
        <div style={{ display: "flex", gap: 2, flexShrink: 0, paddingRight: "var(--space-1)" }}>
          {!confirmDelete ? (
            <>
              <IconButton icon="edit" label={t("chat.rename")} size={24} iconSize={14} onClick={() => { setDraft(label); setEditing(true); }} />
              <IconButton icon="trash" label={t("chat.delete")} size={24} iconSize={14} onClick={() => setConfirmDelete(true)} />
            </>
          ) : (
            <IconButton icon="trash" label={t("chat.confirmDelete")} size={24} iconSize={14} danger onClick={() => onDelete(conv.id)} />
          )}
        </div>
      )}
    </div>
  );
}

function ConversationGroup({ title, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-half)" }}>
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
        {title}
      </div>
      {children}
    </div>
  );
}

export function Sidebar({
  me,
  prefs,
  conversations,
  activeId,
  onSelectConversation,
  onRenameConversation,
  onDeleteConversation,
  onClose,
  onNewChat,
  onOpenProfile,
  onCollapse,
}) {
  const { t } = useLocale();
  const [search, setSearch] = useState("");
  const searchRef = useRef(null);
  const labelFor = (conv) => localizedConversationLabel(conv, t, deriveTitle);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => labelFor(c).toLowerCase().includes(q));
  }, [conversations, search, t]);
  const groups = localizedGroupConversationsByDate(filtered, t);

  useEffect(() => {
    function onKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div
      style={{
        width: "100%",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        boxSizing: "border-box",
        minWidth: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "var(--space-5) var(--space-4) var(--space-4)", gap: "var(--space-2)" }}>
        <SidebarBrand title={t("productName")} subtitle={t("chatSubtitle")} />
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-1)", flexShrink: 0 }}>
          {onCollapse && <RailCollapseButton onClick={onCollapse} label={t("nav.hideChatRail")} />}
          {onClose && <IconButton icon="close" label={t("nav.closeMenu")} onClick={onClose} size={28} iconSize={16} />}
        </div>
      </div>

      <div style={{ padding: "0 var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
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
          <Icon name="plus" size={14} /> {t("chat.newChat")}
        </button>
        <Input
          ref={searchRef}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("chat.searchConversations")}
          style={{ width: "100%", fontSize: "var(--text-sm)" }}
        />
      </div>

      <nav
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "var(--space-4) var(--space-4) var(--space-6)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-5)",
          minHeight: 0,
        }}
      >
        {groups.length === 0 ? (
          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", padding: "0 var(--space-3)" }}>
            {search.trim() ? t("chat.noSearchResults") : t("chat.noConversations")}
          </div>
        ) : (
          groups.map((group) => (
            <ConversationGroup key={group.title} title={group.title}>
              {group.items.map((conv) => (
                <ConversationItem
                  key={conv.id}
                  conv={conv}
                  label={labelFor(conv)}
                  active={conv.id === activeId}
                  streaming={conv.messages.some((m) => m.streaming)}
                  onSelect={onSelectConversation}
                  onRename={onRenameConversation}
                  onDelete={onDeleteConversation}
                />
              ))}
            </ConversationGroup>
          ))
        )}
      </nav>

      <div
        style={{
          borderTop: "1px solid var(--border)",
          padding: "var(--space-4) var(--space-4) var(--space-5)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-3)",
        }}
      >
        {me?.email && (
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            <button
              onClick={onOpenProfile}
              title={t("nav.profile")}
              aria-label={t("nav.profile")}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-3)",
                flex: 1,
                minWidth: 0,
                border: "none",
                background: "transparent",
                cursor: "pointer",
                padding: "var(--space-1) 0",
                textAlign: "left",
                color: "var(--text-primary)",
              }}
            >
              <UserAvatar email={me.email} swatchId={prefs?.avatarSwatch} size={32} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    fontSize: "var(--text-xs)",
                    fontWeight: "var(--weight-semibold)",
                    color: "var(--text-primary)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {prefs?.displayName || me.email}
                </div>
                <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>{localizedRoleLabel(me.role, t)}</div>
              </div>
            </button>
            <IconButton icon="logout" label={t("chat.logout")} size={28} iconSize={16} onClick={() => logout().then(() => (window.location.href = "/login"))} />
          </div>
        )}
        {me?.role === "admin" && (
          <a
            href="/admin/"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--accent)", textDecoration: "none" }}
          >
            {t("nav.openAdmin")} <Icon name="external-link" size={12} style={{ display: "inline", verticalAlign: "middle", marginLeft: 4 }} />
          </a>
        )}
      </div>
      <style>{`
        @keyframes bv-sidebar-stream-pulse {
          0%, 80%, 100% { opacity: 0.35; transform: scale(0.85); }
          40% { opacity: 1; transform: scale(1); }
        }
        @media (prefers-reduced-motion: reduce) {
          [aria-label="Đang trả lời"] { animation: none !important; opacity: 0.8; }
        }
      `}</style>
    </div>
  );
}
