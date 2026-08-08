import { useEffect, useRef, useState } from "react";
import "katex/dist/katex.min.css";
import { useTheme } from "../theme/useTheme.js";
import { Button } from "../components/index.js";
import { Sidebar } from "./Sidebar.jsx";
import { EmptyState } from "./EmptyState.jsx";
import { SourcePanel } from "./SourcePanel.jsx";
import { Composer } from "./Composer.jsx";
import { ChatMessage } from "./ChatMessage.jsx";
import { fetchMe, askStreaming } from "./api.js";

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

// Per-tab conversation persistence (P2-F1, audit/REPORT.md): messages lived
// in plain useState with nothing backing it, so a refresh, accidental
// back-button, or tab close silently destroyed the whole thread — including
// a long multi-turn conversation an employee may have spent several minutes
// building context in. sessionStorage is the smallest fix that closes this:
// no new backend surface, no schema, nothing leaves the browser, and it
// clears itself when the tab closes (matching what a user expects from "the
// chat I currently have open", not a permanent server-side history).
const STORAGE_KEY = "bv-chat-messages";

function loadStoredMessages() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // A message still marked "streaming" was mid-flight when the tab closed
    // or the page was left — that request is gone now, so it must not be
    // rendered as still-in-progress (it would show the "Đang tìm..."
    // indicator forever with no fetch behind it).
    const restored = parsed.map((m) => ({ ...m, streaming: false }));
    // If the very last turn was an assistant message that never received any
    // content (reload/close landed before the first token), drop it rather
    // than show a permanently blank bubble with only "Tạo lại" — the user's
    // question is still there to resend or the regenerate flow still needs
    // a real prior turn to work from.
    const last = restored[restored.length - 1];
    if (last && last.role === "assistant" && !last.text) restored.pop();
    return restored;
  } catch {
    return [];
  }
}

export function ChatScreen() {
  const [theme, setTheme] = useTheme();
  const [me, setMe] = useState(null);
  const [messages, setMessages] = useState(loadStoredMessages);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [citation, setCitation] = useState(null);
  const [railOpen, setRailOpen] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);
  const abortRef = useRef(null);
  const mobile = useIsMobile();

  useEffect(() => {
    fetchMe().then(setMe).catch(() => setMe(null));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  useEffect(() => {
    try {
      if (messages.length === 0) sessionStorage.removeItem(STORAGE_KEY);
      else sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {
      // Private-browsing quota or storage disabled — persistence is a
      // nice-to-have degradation, not a reason to break the chat itself.
    }
  }, [messages]);

  async function send(queryText) {
    const query = queryText.trim();
    if (!query || busy) return;
    setInput("");
    setCitation(null);
    setError(null);
    const history = messages.map((m) => ({ role: m.role, content: m.text }));
    const nextMessages = [...messages, { role: "user", text: query }, { role: "assistant", text: "", streaming: true }];
    setMessages(nextMessages);
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await askStreaming(
        [...history, { role: "user", content: query }],
        (delta) => {
          setMessages((prev) => {
            const copy = prev.slice();
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { ...last, text: last.text + delta };
            return copy;
          });
        },
        controller.signal,
      );
    } catch (err) {
      // A user-initiated stop (see stop() below) throws AbortError — that's
      // the expected, silent outcome, not a failure to surface. Whatever
      // partial text already streamed in stays on screen as-is.
      if (err.name !== "AbortError") setError(err.message);
    } finally {
      setMessages((prev) => {
        const copy = prev.slice();
        const last = copy[copy.length - 1];
        copy[copy.length - 1] = { ...last, streaming: false };
        return copy;
      });
      setBusy(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function regenerate(assistantIndex) {
    const userMessage = messages[assistantIndex - 1];
    if (!userMessage || userMessage.role !== "user") return;
    setMessages(messages.slice(0, assistantIndex - 1));
    send(userMessage.text);
  }

  function newChat() {
    setMessages([]);
    setCitation(null);
    setRailOpen(false);
  }

  const sidebarProps = { me, theme, onTheme: setTheme, onNewChat: newChat };

  return (
    <div data-theme={theme} style={{ height: "100vh", display: "flex", fontFamily: "var(--font-sans)", background: "var(--bg)", overflow: "hidden" }}>
      {!mobile && <Sidebar {...sidebarProps} />}
      {mobile && railOpen && (
        <div onClick={() => setRailOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(6,18,30,.5)", backdropFilter: "blur(2px)", zIndex: 20 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ position: "absolute", left: 0, top: 0, bottom: 0, boxShadow: "var(--shadow-lg)" }}>
            <Sidebar {...sidebarProps} onClose={() => setRailOpen(false)} />
          </div>
        </div>
      )}

      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, height: "100%" }}>
        <header style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", height: 56, flexShrink: 0, padding: mobile ? "0 var(--space-4)" : "0 var(--space-5) 0 var(--space-8)", borderBottom: "1px solid var(--border)", background: "var(--bg)" }}>
          {mobile && (
            <Button
              variant="ghost"
              onClick={() => setRailOpen(true)}
              aria-label="Mở menu"
              style={{ border: "none", fontSize: 17, color: "var(--text-primary)", padding: 0, width: 32, height: 32 }}
            >
              ☰
            </Button>
          )}
          <div style={{ minWidth: 0, fontSize: "var(--text-sm)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {messages.length === 0 ? "Cuộc trò chuyện mới" : messages[0]?.text}
          </div>
        </header>

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }}>
              {messages.length === 0 ? (
                <EmptyState me={me} onPick={send} />
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
                    />
                  ))}
                  {error && <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--danger)" }}>Lỗi: {error}</p>}
                </div>
              )}
            </div>
            <Composer value={input} onChange={setInput} onSend={() => send(input)} onStop={stop} disabled={busy} mobile={mobile} />
          </div>
          {!mobile && citation && <SourcePanel citation={citation} onClose={() => setCitation(null)} />}
        </div>
      </main>
    </div>
  );
}
