import { useEffect, useRef, useState } from "react";
import "katex/dist/katex.min.css";
import { useTheme } from "../theme/useTheme.js";
import { IconButton, Modal, RailExpandButton, ResizableRail, AppHeader, useRailLayout } from "../components/index.js";
import { localizedConversationLabel } from "../i18n/catalog.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { ProfileView } from "../user/ProfileView.jsx";
import { useProfilePrefs } from "../user/useProfilePrefs.js";
import { Sidebar } from "./Sidebar.jsx";
import { EmptyState } from "./EmptyState.jsx";
import { SourcePanel, SourcePanelContent } from "./SourcePanel.jsx";
import { Composer } from "./Composer.jsx";
import { ChatMessage } from "./ChatMessage.jsx";
import { changePassword, fetchMe, askStreaming, logout, sendFeedback } from "./api.js";
import { DocumentUploadModal } from "./DocumentUploadModal.jsx";
import {
  exportAllConversationsJson,
  exportConversationJson,
  exportConversationMarkdown,
} from "./conversationExport.js";
import { deleteConversationOnServer } from "./conversationApi.js";
import {
  deleteAllConversationsOnServer,
  loadServerConversationsState,
  persistConversationsState,
} from "./conversationStore.js";
import {
  clearAllConversationsState,
  conversationLabel,
  deriveTitle,
  generateConversationId,
  pruneEmptyConversations,
  sanitizeMessages,
} from "./conversations.js";

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

function viewFromHash() {
  return window.location.hash === "#profile" ? "profile" : "chat";
}

function isConversationStreaming(conv) {
  return conv?.messages?.some((m) => m.streaming) ?? false;
}

export function ChatScreen() {
  const { t } = useLocale();
  const { theme, preference, setTheme, toggleTheme } = useTheme();
  const [me, setMe] = useState(null);
  const [prefs, setPrefs, hydrateFromServer] = useProfilePrefs(me?.email);
  const [convState, setConvState] = useState({ conversations: [], activeId: null, loaded: false });
  const { conversations, activeId, loaded } = convState;
  const [view, setView] = useState(viewFromHash);
  const [input, setInput] = useState("");
  const [citation, setCitation] = useState(null);
  const [railOpen, setRailOpen] = useState(false);
  const [error, setError] = useState(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const scrollRef = useRef(null);
  /** In-flight streams keyed by conversation — survives navigation within chat. */
  const streamsRef = useRef(new Map());
  const mobile = useIsMobile();
  const railLayout = useRailLayout("bv-rail-chat");

  const activeConversation = conversations.find((c) => c.id === activeId);
  const messages = activeConversation?.messages ?? [];
  const activeConvStreaming = isConversationStreaming(activeConversation);
  const anyStreaming = conversations.some(isConversationStreaming);

  useEffect(() => {
    fetchMe()
      .then((data) => {
        setMe(data);
        if (data?.email) hydrateFromServer(data);
      })
      .catch(() => setMe(null));
    loadServerConversationsState().then(({ conversations, activeId }) => {
      setConvState({ conversations, activeId, loaded: true });
    });
  }, [hydrateFromServer]);

  useEffect(() => {
    if (!loaded) return;
    const timer = setTimeout(() => {
      persistConversationsState(conversations, activeId);
    }, 400);
    return () => clearTimeout(timer);
  }, [conversations, activeId, loaded]);

  useEffect(() => {
    const base = t("productName");
    document.title = anyStreaming ? `● ${base}` : base;
  }, [anyStreaming, t]);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const scrollKey = `${activeId}:${messages.length}:${messages[messages.length - 1]?.text?.length ?? 0}`;
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [scrollKey]);

  function patchConversation(convId, patchFn) {
    setConvState((prev) => ({
      ...prev,
      conversations: prev.conversations.map((c) => (c.id === convId ? patchFn(c) : c)),
    }));
  }

  function abortConversationStream(convId) {
    streamsRef.current.get(convId)?.abort();
  }

  function openProfile() {
    window.location.hash = "profile";
    setView("profile");
    setRailOpen(false);
  }

  function closeProfile() {
    if (window.location.hash === "#profile") {
      history.replaceState(null, "", window.location.pathname + window.location.search);
    }
    setView("chat");
  }

  async function send(queryText) {
    const query = queryText.trim();
    if (!query || isConversationStreaming(activeConversation)) return;
    const convId = activeId;
    if (!convId) return;

    setInput("");
    setCitation(null);
    setError(null);
    const history = messages.map((m) => ({ role: m.role, content: m.text }));
    const nextMessages = [...messages, { role: "user", text: query }, { role: "assistant", text: "", streaming: true }];
    patchConversation(convId, (c) => ({
      ...c,
      messages: nextMessages,
      title: c.customTitle ? c.title : deriveTitle(nextMessages),
      updatedAt: Date.now(),
    }));
    const controller = new AbortController();
    streamsRef.current.set(convId, controller);
    let completionId = null;
    try {
      completionId = await askStreaming(
        [...history, { role: "user", content: query }],
        (delta) => {
          patchConversation(convId, (c) => {
            const copy = c.messages.slice();
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { ...last, text: last.text + delta };
            return { ...c, messages: copy, updatedAt: Date.now() };
          });
        },
        controller.signal,
      );
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
    } finally {
      streamsRef.current.delete(convId);
      patchConversation(convId, (c) => {
        const copy = c.messages.slice();
        const last = copy[copy.length - 1];
        if (last?.role === "assistant") {
          copy[copy.length - 1] = { ...last, streaming: false, completionId };
        }
        const sanitized = sanitizeMessages(copy);
        return {
          ...c,
          messages: sanitized,
          title: c.customTitle ? c.title : deriveTitle(sanitized),
          updatedAt: Date.now(),
        };
      });
    }
  }

  function stop() {
    if (activeId) abortConversationStream(activeId);
  }

  const [feedbackSent, setFeedbackSent] = useState({});
  async function giveFeedback(index) {
    const msg = messages[index];
    if (!msg?.completionId || feedbackSent[index]) return;
    setFeedbackSent((prev) => ({ ...prev, [index]: true }));
    try {
      await sendFeedback(msg.completionId, null);
    } catch {
      setFeedbackSent((prev) => ({ ...prev, [index]: false }));
    }
  }

  function regenerate(assistantIndex) {
    const userMessage = messages[assistantIndex - 1];
    if (!userMessage || userMessage.role !== "user" || activeConvStreaming) return;
    patchConversation(activeId, (c) => ({
      ...c,
      messages: c.messages.slice(0, assistantIndex - 1),
      updatedAt: Date.now(),
    }));
    send(userMessage.text);
  }

  function newChat() {
    const id = generateConversationId();
    setConvState((prev) => ({
      ...prev,
      activeId: id,
      conversations: pruneEmptyConversations(
        [{ id, title: t("chat.newChat"), messages: [], updatedAt: Date.now() }, ...prev.conversations],
        id,
      ),
    }));
    setCitation(null);
    setError(null);
    setFeedbackSent({});
    setRailOpen(false);
    closeProfile();
  }

  function selectConversation(id) {
    if (id === activeId) {
      setRailOpen(false);
      return;
    }
    setConvState((prev) => ({
      ...prev,
      activeId: id,
      conversations: pruneEmptyConversations(prev.conversations, id),
    }));
    setCitation(null);
    setError(null);
    setFeedbackSent({});
    setRailOpen(false);
    closeProfile();
  }

  function renameConversation(id, title) {
    setConvState((prev) => ({
      ...prev,
      conversations: prev.conversations.map((c) =>
        c.id === id ? { ...c, customTitle: title, title, updatedAt: Date.now() } : c,
      ),
    }));
  }

  function deleteConversation(id) {
    abortConversationStream(id);
    streamsRef.current.delete(id);
    deleteConversationOnServer(id).catch(() => {});
    setConvState((prev) => {
      const remaining = prev.conversations.filter((c) => c.id !== id);
      if (remaining.length === 0) {
        const newId = generateConversationId();
        return {
          ...prev,
          activeId: newId,
          conversations: [{ id: newId, title: t("chat.newChat"), messages: [], updatedAt: Date.now() }],
        };
      }
      const nextActive = id === prev.activeId ? remaining[0].id : prev.activeId;
      return { ...prev, activeId: nextActive, conversations: remaining };
    });
    setCitation(null);
    setFeedbackSent({});
  }

  function clearAllConversations() {
    for (const controller of streamsRef.current.values()) {
      controller.abort();
    }
    streamsRef.current.clear();
    deleteAllConversationsOnServer()
      .catch(() => {})
      .finally(() => {
        setConvState({ ...clearAllConversationsState(), loaded: true });
        setCitation(null);
        setError(null);
        setFeedbackSent({});
      });
  }

  const sidebarProps = {
    me,
    prefs,
    conversations,
    activeId,
    onSelectConversation: selectConversation,
    onRenameConversation: renameConversation,
    onDeleteConversation: deleteConversation,
    onNewChat: newChat,
    onOpenProfile: openProfile,
  };

  const headerTitle =
    view === "profile"
      ? t("nav.profile")
      : messages.length === 0
        ? t("productName")
        : activeConversation
          ? localizedConversationLabel(activeConversation, t, deriveTitle)
          : messages[0]?.text;

  const conversationCount = conversations.filter((c) => c.messages.length > 0).length;

  return (
    <div data-theme={theme} style={{ height: "100vh", display: "flex", fontFamily: "var(--font-sans)", background: "var(--bg)", overflow: "hidden" }}>
      {!mobile && (
        <ResizableRail layout={railLayout} collapseLabel={t("nav.hideChatRail")}>
          <Sidebar {...sidebarProps} onCollapse={railLayout.collapse} />
        </ResizableRail>
      )}
      {mobile && railOpen && (
        <div onClick={() => setRailOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(6,18,30,.5)", backdropFilter: "blur(2px)", zIndex: 20 }}>
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: `min(${railLayout.width}px, 85vw)`,
              boxShadow: "var(--shadow-lg)",
              background: "var(--surface)",
              borderRight: "1px solid var(--border)",
            }}
          >
            <Sidebar {...sidebarProps} onClose={() => setRailOpen(false)} />
          </div>
        </div>
      )}

      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, height: "100%" }}>
        <AppHeader
          title={headerTitle}
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
          expand={!mobile && railLayout.collapsed ? <RailExpandButton onClick={railLayout.expand} label={t("nav.showChatRail")} /> : null}
        />

        <DocumentUploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} />

        {view === "profile" ? (
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
            backLabel={t("nav.backChat")}
            conversationCount={conversationCount}
            onClearConversations={clearAllConversations}
            conversations={conversations.filter((c) => c.messages.length > 0)}
            activeConversation={activeConversation?.messages?.length ? activeConversation : null}
            onExportAll={() => exportAllConversationsJson(conversations.filter((c) => c.messages.length > 0))}
            onExportActiveMarkdown={() =>
              activeConversation &&
              exportConversationMarkdown(activeConversation, {
                fallbackTitle: t("chat.exportFallbackTitle"),
                user: t("chat.exportUser"),
                assistant: t("chat.exportAssistant"),
              })
            }
            onExportActiveJson={() => activeConversation && exportConversationJson(activeConversation)}
          />
        ) : !loaded ? (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
            {t("chat.loadingConversations")}
          </div>
        ) : (
          <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
              <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }}>
                {messages.length === 0 ? (
                  <EmptyState me={me} displayName={prefs.displayName} onPick={send} />
                ) : (
                  <div
                    style={{
                      width: "100%",
                      maxWidth: "var(--content-max)",
                      margin: "0 auto",
                      boxSizing: "border-box",
                      padding: mobile ? "var(--space-5) var(--space-4)" : "var(--space-8)",
                      display: "flex",
                      flexDirection: "column",
                      gap: "var(--space-8)",
                    }}
                  >
                    {messages.map((m, i) => (
                      <ChatMessage
                        key={i}
                        role={m.role}
                        text={m.text}
                        streaming={m.streaming}
                        active={citation}
                        onOpen={setCitation}
                        onRegenerate={m.role === "assistant" && !m.streaming ? () => regenerate(i) : null}
                        onFeedback={m.role === "assistant" && !m.streaming && m.completionId ? () => giveFeedback(i) : null}
                        feedbackSent={!!feedbackSent[i]}
                      />
                    ))}
                    {error && <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--danger)" }}>{t("common.error")}: {error}</p>}
                  </div>
                )}
              </div>
              <Composer
                value={input}
                onChange={setInput}
                onSend={() => send(input)}
                onStop={stop}
                onUpload={me?.role === "admin" ? () => setUploadOpen(true) : undefined}
                disabled={activeConvStreaming}
                mobile={mobile}
              />
            </div>
            {!mobile && citation && <SourcePanel citation={citation} onClose={() => setCitation(null)} />}
          </div>
        )}
      </main>

      {citation && mobile && (
        <Modal open title={t("chat.sourceN", { n: citation.n })} onClose={() => setCitation(null)}>
          <SourcePanelContent citation={citation} />
        </Modal>
      )}
    </div>
  );
}
