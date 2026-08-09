import {
  deleteAllConversationsOnServer as deleteAllConversationsApi,
  fetchConversations,
  syncConversations,
} from "./conversationApi.js";
import {
  generateConversationId,
  loadConversationsState,
  sanitizeConversation,
  sanitizeMessages,
} from "./conversations.js";

const LEGACY_KEY = "bv-chat-messages";
const LEGACY_CONV_KEY = "bv-chat-conversations";
const LEGACY_ACTIVE_KEY = "bv-chat-active-id";

function readSessionLegacy() {
  try {
    const raw = sessionStorage.getItem(LEGACY_KEY);
    if (!raw) return null;
    const messages = sanitizeMessages(JSON.parse(raw));
    sessionStorage.removeItem(LEGACY_KEY);
    return messages;
  } catch {
    return null;
  }
}

function readSessionConversations() {
  try {
    const raw = sessionStorage.getItem(LEGACY_CONV_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const activeId = sessionStorage.getItem(LEGACY_ACTIVE_KEY);
    sessionStorage.removeItem(LEGACY_CONV_KEY);
    sessionStorage.removeItem(LEGACY_ACTIVE_KEY);
    if (!Array.isArray(parsed)) return null;
    return { conversations: parsed, activeId };
  } catch {
    return null;
  }
}

/** Load conversations from the server; migrate one-time sessionStorage data. */
export async function loadServerConversationsState() {
  let local = loadConversationsState();
  const legacyMessages = readSessionLegacy();
  const sessionBackup = readSessionConversations();

  if (sessionBackup?.conversations?.length) {
    local = {
      conversations: sessionBackup.conversations,
      activeId: sessionBackup.activeId ?? sessionBackup.conversations[0]?.id,
    };
  } else if (legacyMessages?.length && local.conversations.every((c) => c.messages.length === 0)) {
    const id = generateConversationId();
    local = {
      conversations: [{ id, title: "Cuộc trò chuyện mới", messages: legacyMessages, updatedAt: Date.now() }],
      activeId: id,
    };
  }

  try {
    const server = await fetchConversations();
    if (server.conversations.length > 0) {
      return {
        conversations: server.conversations.map(sanitizeConversation),
        activeId: server.activeId ?? server.conversations[0].id,
      };
    }
    if (local.conversations.some((c) => c.messages.length > 0)) {
      const synced = await syncConversations(local.conversations, local.activeId);
      return {
        conversations: synced.conversations.map(sanitizeConversation),
        activeId: synced.activeId,
      };
    }
    return {
      conversations: local.conversations.map(sanitizeConversation),
      activeId: local.activeId,
    };
  } catch {
    return {
      conversations: local.conversations.map(sanitizeConversation),
      activeId: local.activeId,
    };
  }
}

export async function persistConversationsState(conversations, activeId) {
  try {
    await syncConversations(conversations, activeId);
  } catch {
    // Degrade silently — user keeps working in-memory for this tab.
  }
}

export async function deleteAllConversationsOnServer() {
  await deleteAllConversationsApi();
}
