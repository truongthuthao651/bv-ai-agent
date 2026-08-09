import { useEffect, useMemo, useRef, useState } from "react";
import { Input, RailCollapseButton } from "../components/index.js";
import { UserAvatar } from "../components/user/UserAvatar.jsx";
import { roleLabel } from "../user/profilePrefs.js";
import { logout } from "./api.js";
import { conversationLabel, filterConversations, groupConversationsByDate } from "./conversations.js";

function ConversationItem({ conv, active, streaming, onSelect, onRename, onDelete }) {
  const [hover, setHover] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conversationLabel(conv));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const label = conversationLabel(conv);

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
            title="Đang trả lời…"
            aria-label="Đang trả lời"
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
              <button
                type="button"
                title="Đổi tên"
                aria-label="Đổi tên cuộc trò chuyện"
                onClick={() => {
                  setDraft(label);
                  setEditing(true);
                }}
                style={iconBtnStyle}
              >
                ✎
              </button>
              <button
                type="button"
                title="Xóa"
                aria-label="Xóa cuộc trò chuyện"
                onClick={() => setConfirmDelete(true)}
                style={iconBtnStyle}
              >
                ✕
              </button>
            </>
          ) : (
            <button
              type="button"
              title="Xác nhận xóa"
              aria-label="Xác nhận xóa cuộc trò chuyện"
              onClick={() => onDelete(conv.id)}
              style={{ ...iconBtnStyle, color: "var(--danger)" }}
            >
              🗑
            </button>
          )}
        </div>
      )}
    </div>
  );
}

const iconBtnStyle = {
  border: "none",
  background: "transparent",
  color: "var(--text-muted)",
  cursor: "pointer",
  fontSize: 12,
  padding: "2px 4px",
  lineHeight: 1,
};

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
  const [search, setSearch] = useState("");
  const searchRef = useRef(null);
  const filtered = useMemo(() => filterConversations(conversations, search), [conversations, search]);

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
  const groups = groupConversationsByDate(filtered);

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
        <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-bold)", color: "var(--text-primary)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          Trợ lý AI Bảo Việt Life
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-1)", flexShrink: 0 }}>
          {onCollapse && <RailCollapseButton onClick={onCollapse} label="Ẩn danh sách trò chuyện" />}
          {onClose && (
            <button onClick={onClose} aria-label="Đóng menu" style={{ border: "none", background: "transparent", color: "var(--text-muted)", fontSize: 16, cursor: "pointer" }}>
              ✕
            </button>
          )}
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
          <span style={{ fontSize: 15, lineHeight: 1 }}>+</span> Cuộc trò chuyện mới
        </button>
        <Input
          ref={searchRef}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Tìm cuộc trò chuyện… (⌘K)"
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
            {search.trim() ? "Không tìm thấy cuộc trò chuyện nào." : "Chưa có cuộc trò chuyện."}
          </div>
        ) : (
          groups.map((group) => (
            <ConversationGroup key={group.title} title={group.title}>
              {group.items.map((conv) => (
                <ConversationItem
                  key={conv.id}
                  conv={conv}
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
              title="Hồ sơ cá nhân"
              aria-label="Hồ sơ cá nhân"
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
                <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>{roleLabel(me.role)}</div>
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
          <a
            href="/admin/"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--accent)", textDecoration: "none" }}
          >
            Mở trang quản trị ↗
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
