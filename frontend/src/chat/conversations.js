/** Per-tab multi-conversation persistence in sessionStorage.
 *  Each tab keeps its own thread list; nothing is sent to the server. */

const CONVERSATIONS_KEY = "bv-chat-conversations";
const ACTIVE_KEY = "bv-chat-active-id";
const LEGACY_KEY = "bv-chat-messages";

export function generateConversationId() {
  return `conv-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function deriveTitle(messages) {
  const firstUser = messages.find((m) => m.role === "user" && m.text?.trim());
  if (!firstUser) return "Cuộc trò chuyện mới";
  const text = firstUser.text.trim();
  return text.length > 48 ? `${text.slice(0, 48)}…` : text;
}

/** Strip half-finished turns so a restored tab never shows a stuck spinner. */
export function sanitizeMessages(parsed) {
  if (!Array.isArray(parsed)) return [];
  const restored = parsed.map((m) => ({ ...m, streaming: false }));
  const last = restored[restored.length - 1];
  if (last && last.role === "assistant" && !last.text) restored.pop();
  return restored;
}

/** Apply message sanitization to one conversation object. */
export function sanitizeConversation(conv) {
  const messages = sanitizeMessages(conv.messages ?? []);
  return {
    ...conv,
    messages,
    title: conv.customTitle ? conv.title : deriveTitle(messages),
  };
}

function readJson(key) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function loadConversationsState() {
  try {
    let conversations = readJson(CONVERSATIONS_KEY);
    if (!Array.isArray(conversations)) conversations = [];

    let activeId = sessionStorage.getItem(ACTIVE_KEY);

    // One-time migration from the pre-multi-thread single-key storage.
    const legacy = readJson(LEGACY_KEY);
    if (legacy && conversations.length === 0) {
      const messages = sanitizeMessages(legacy);
      if (messages.length > 0) {
        const id = generateConversationId();
        conversations = [
          { id, title: deriveTitle(messages), messages, updatedAt: Date.now() },
        ];
        activeId = id;
      }
      sessionStorage.removeItem(LEGACY_KEY);
    }

    if (conversations.length === 0) {
      const id = generateConversationId();
      conversations = [{ id, title: "Cuộc trò chuyện mới", messages: [], updatedAt: Date.now() }];
      activeId = id;
    } else if (!activeId || !conversations.some((c) => c.id === activeId)) {
      activeId = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt)[0].id;
    }

    return { conversations, activeId };
  } catch {
    const id = generateConversationId();
    return {
      conversations: [{ id, title: "Cuộc trò chuyện mới", messages: [], updatedAt: Date.now() }],
      activeId: id,
    };
  }
}

export function saveConversationsState(conversations, activeId) {
  try {
    sessionStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
    sessionStorage.setItem(ACTIVE_KEY, activeId);
  } catch {
    // Private-browsing quota — persistence degrades silently.
  }
}

/** Drop blank drafts so the rail doesn't fill with empty "new chat" rows. */
export function pruneEmptyConversations(conversations, keepId) {
  return conversations.filter((c) => c.id === keepId || c.messages.length > 0);
}

export function conversationLabel(conv) {
  return conv.customTitle ?? conv.title ?? deriveTitle(conv.messages ?? []);
}

export function filterConversations(conversations, query) {
  const q = query.trim().toLowerCase();
  if (!q) return conversations;
  return conversations.filter((c) => conversationLabel(c).toLowerCase().includes(q));
}

export function clearAllConversationsState() {
  const id = generateConversationId();
  return {
    conversations: [{ id, title: "Cuộc trò chuyện mới", messages: [], updatedAt: Date.now() }],
    activeId: id,
  };
}

export function groupConversationsByDate(conversations) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;

  const sorted = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);
  const today = [];
  const yesterday = [];
  const older = [];

  for (const conv of sorted) {
    if (conv.updatedAt >= startOfToday) today.push(conv);
    else if (conv.updatedAt >= startOfYesterday) yesterday.push(conv);
    else older.push(conv);
  }

  const groups = [];
  if (today.length) groups.push({ title: "Hôm nay", items: today });
  if (yesterday.length) groups.push({ title: "Hôm qua", items: yesterday });
  if (older.length) groups.push({ title: "Trước đó", items: older });
  return groups;
}
