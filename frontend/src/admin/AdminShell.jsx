import { useEffect, useMemo, useState } from "react";
import { AppHeader, Badge, Icon, IconButton, RailCollapseButton, RailExpandButton, ResizableRail, SidebarBrand, UserAvatar, useRailLayout } from "../components/index.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { localizedRoleLabel } from "../i18n/catalog.js";
import { useTheme } from "../theme/useTheme.js";
import { ProfileView } from "../user/ProfileView.jsx";
import { useProfilePrefs } from "../user/useProfilePrefs.js";
import { deleteAllConversationsOnServer } from "../chat/conversationStore.js";
import { EvaluationView, LogsView, ModelsView, SettingsView } from "./AdminOpsViews.jsx";
import { changePassword, fetchConversationCount, fetchHealth, fetchMe, logout } from "./api.js";
import { OverviewView } from "./OverviewView.jsx";
import { DocumentsView } from "./DocumentsView.jsx";
import { UsersView } from "./UsersView.jsx";

const NAV_KEYS = new Set(["overview", "evaluation", "logs", "documents", "users", "models", "settings"]);

function navGroups(t) {
  return [
    {
      title: t("nav.monitor"),
      items: [
        { key: "overview", label: t("nav.overview") },
        { key: "evaluation", label: t("nav.evaluation") },
        { key: "logs", label: t("nav.logs") },
      ],
    },
    {
      title: t("nav.content"),
      items: [
        { key: "documents", label: t("nav.documents") },
        { key: "users", label: t("nav.users") },
      ],
    },
    {
      title: t("nav.configure"),
      items: [
        { key: "models", label: t("nav.models") },
        { key: "settings", label: t("nav.settings") },
      ],
    },
  ];
}

function navFromHash() {
  const key = window.location.hash.slice(1);
  if (key === "profile") return "profile";
  const base = key.split("/")[0];
  return NAV_KEYS.has(base) ? base : "overview";
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
  const { t } = useLocale();
  const { theme, preference, setTheme, toggleTheme } = useTheme();
  const nav = useMemo(() => navGroups(t), [t]);
  const [active, setActive] = useState(navFromHash);
  const [hoverNav, setHoverNav] = useState(null);
  const [health, setHealth] = useState(null);
  const [me, setMe] = useState(null);
  const [prefs, setPrefs, hydrateFromServer] = useProfilePrefs(me?.email);
  const [conversationCount, setConversationCount] = useState(0);
  const [railOpen, setRailOpen] = useState(false);
  const mobile = useIsMobile();
  const railLayout = useRailLayout("bv-rail-admin");

  useEffect(() => {
    fetchMe()
      .then((data) => {
        setMe(data);
        if (data?.email) hydrateFromServer(data);
      })
      .catch(() => setMe(null));
  }, [hydrateFromServer]);

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

  function openProfile() {
    window.location.hash = "profile";
    setActive("profile");
    setRailOpen(false);
  }

  function closeProfile() {
    if (window.location.hash === "#profile") {
      window.location.hash = "overview";
    }
    setActive("overview");
  }

  useEffect(() => {
    if (!me?.email) return;
    fetchConversationCount().then(setConversationCount).catch(() => setConversationCount(0));
  }, [me?.email, active]);

  function clearAllConversations() {
    return deleteAllConversationsOnServer().then(() => setConversationCount(0));
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
  const railContent = (onCollapse) => (
    <>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "var(--space-2)", padding: "var(--space-5) var(--space-4) var(--space-6)" }}>
        <SidebarBrand title={t("productName")} subtitle={t("adminSubtitle")} />
        {onCollapse && <RailCollapseButton onClick={onCollapse} label={t("nav.hideAdminRail")} />}
      </div>

      <nav style={{ flex: 1, overflowY: "auto", padding: "0 var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-6)", minHeight: 0 }}>
        {nav.map((g) => (
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

      <div style={{ borderTop: "1px solid var(--border)", padding: "var(--space-4) var(--space-4) var(--space-5)", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {me?.email && (
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            <button
              onClick={openProfile}
              title={t("nav.profile")}
              aria-label={t("nav.profile")}
              style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flex: 1, minWidth: 0, border: "none", background: "transparent", cursor: "pointer", padding: "var(--space-1) 0", textAlign: "left", color: "var(--text-primary)" }}
            >
              <UserAvatar email={me.email} swatchId={prefs.avatarSwatch} size={32} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {prefs.displayName || me.email}
                </div>
                <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>{localizedRoleLabel(me.role, t)}</div>
              </div>
            </button>
            <IconButton icon="logout" label={t("chat.logout")} size={28} iconSize={16} onClick={handleLogout} />
          </div>
        )}
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
          <Badge label={`Ollama: ${ollamaStatus === "up" ? t("admin.serviceUp") : t("admin.serviceDown")}`} status={ollamaStatus === "up" ? "ok" : "bad"} />
          <Badge label={`Qdrant: ${qdrantStatus === "up" ? t("admin.serviceUp") : t("admin.serviceDown")}`} status={qdrantStatus === "up" ? "ok" : "bad"} />
        </div>
        <a
          href="/chat/"
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--accent)", textDecoration: "none" }}
        >
          {t("nav.openChat")} <Icon name="external-link" size={12} style={{ display: "inline", verticalAlign: "middle", marginLeft: 4 }} />
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
        <ResizableRail layout={railLayout} collapseLabel={t("nav.hideAdminRail")}>
          {railContent(railLayout.collapse)}
        </ResizableRail>
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
              width: `min(${railLayout.width}px, 85vw)`,
              maxWidth: "85vw",
              background: "var(--surface)",
              display: "flex",
              flexDirection: "column",
              boxSizing: "border-box",
              boxShadow: "var(--shadow-lg)",
              borderRight: "1px solid var(--border)",
            }}
          >
            {railContent(null)}
          </div>
        </div>
      )}

      <main style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <AppHeader
          title={
            active === "profile"
              ? t("nav.profile")
              : nav.flatMap((g) => g.items).find((it) => it.key === active)?.label
          }
          theme={theme}
          onTheme={toggleTheme}
          menu={
            mobile ? (
              <IconButton
                icon="menu"
                label={t("nav.openMenu")}
                onClick={() => setRailOpen(true)}
                size={32}
                iconSize={18}
                color="var(--text-primary)"
                style={{ background: "transparent" }}
              />
            ) : null
          }
          expand={!mobile && railLayout.collapsed ? <RailExpandButton onClick={railLayout.expand} label={t("nav.showAdminRail")} /> : null}
        />

        {active === "profile" ? (
          <ProfileView
            me={me}
            prefs={prefs}
            onPrefsChange={setPrefs}
            theme={theme}
            themePreference={preference}
            onThemePreference={setTheme}
            onChangePassword={changePassword}
            onLogout={logout}
            onBack={closeProfile}
            backLabel={t("nav.backAdmin")}
            conversationCount={conversationCount}
            onClearConversations={clearAllConversations}
          />
        ) : (
        <div style={{ flex: 1, overflowY: "auto", padding: "var(--pad-page) var(--pad-page) var(--space-16)" }}>
          <div style={{ maxWidth: 1400, margin: "0 auto" }}>
            {active === "overview" && <OverviewView />}
            {active === "documents" && <DocumentsView canManage={me?.role === "admin"} />}
            {active === "users" && <UsersView />}
            {active === "evaluation" && <EvaluationView />}
            {active === "logs" && <LogsView />}
            {active === "models" && <ModelsView />}
            {active === "settings" && <SettingsView />}
          </div>
        </div>
        )}
      </main>
    </div>
  );
}
