/** Server-backed conversation storage — scoped to the signed-in user only. */

async function asJson(resp) {
  return resp.json().catch(() => ({}));
}

function toPayload(conv) {
  return {
    id: conv.id,
    title: conv.title,
    customTitle: conv.customTitle ?? null,
    messages: conv.messages ?? [],
    updatedAt: conv.updatedAt,
  };
}

function fromPayload(row) {
  return {
    id: row.id,
    title: row.title,
    customTitle: row.customTitle ?? null,
    messages: row.messages ?? [],
    updatedAt: row.updatedAt,
  };
}

export async function fetchConversations() {
  const resp = await fetch("/conversations");
  if (!resp.ok) {
    const data = await asJson(resp);
    throw new Error(data.detail || `HTTP ${resp.status}`);
  }
  const data = await resp.json();
  return {
    conversations: (data.conversations ?? []).map(fromPayload),
    activeId: data.activeId ?? null,
  };
}

export async function syncConversations(conversations, activeId) {
  const resp = await fetch("/conversations/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversations: conversations.map(toPayload),
      activeId,
    }),
  });
  if (!resp.ok) {
    const data = await asJson(resp);
    throw new Error(data.detail || `HTTP ${resp.status}`);
  }
  const data = await resp.json();
  return {
    conversations: (data.conversations ?? []).map(fromPayload),
    activeId: data.activeId ?? null,
  };
}

export async function deleteConversationOnServer(convId) {
  const resp = await fetch(`/conversations/${encodeURIComponent(convId)}`, { method: "DELETE" });
  if (!resp.ok) {
    const data = await asJson(resp);
    throw new Error(data.detail || `HTTP ${resp.status}`);
  }
}

export async function deleteAllConversationsOnServer() {
  const resp = await fetch("/conversations", { method: "DELETE" });
  if (!resp.ok) {
    const data = await asJson(resp);
    throw new Error(data.detail || `HTTP ${resp.status}`);
  }
}

export { fromPayload, toPayload };
