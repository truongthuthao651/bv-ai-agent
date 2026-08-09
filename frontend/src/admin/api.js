/** Thin fetch wrappers over the FastAPI admin endpoints. Same paths and
 *  error shapes the backend exposes — called from the React admin console. */

async function asJson(resp) {
  return resp.json().catch(() => ({}));
}

export async function fetchHealth() {
  const resp = await fetch("/health");
  return asJson(resp);
}

/** The signed-in account ({ email, role } or { email: null, role: null }) —
 *  real identity, never fabricated (see AdminShell.jsx's sidebar footer). */
export async function fetchMe() {
  const resp = await fetch("/me");
  return asJson(resp);
}

/** All provisioned accounts (email + role only) — admin-only. */
export async function fetchAccounts() {
  const resp = await fetch("/accounts");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchMetrics(hours) {
  const resp = await fetch(`/metrics/summary?hours=${encodeURIComponent(hours)}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchDocuments() {
  const resp = await fetch("/documents");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export { uploadDocument } from "../documents/uploadApi.js";

export async function updateDocument(docId, patch) {
  const resp = await fetch(`/documents/${encodeURIComponent(docId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  const data = await asJson(resp);
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

export async function deleteDocument(docId) {
  const resp = await fetch(`/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
  const data = await asJson(resp);
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

export async function logout() {
  await fetch("/logout", { method: "POST" }).catch(() => {});
}

/** P2-J6 (audit/REPORT.md): the minimum viable self-service surface — change
 * the signed-in account's own password. The target account always comes
 * from the session server-side; there is no email field to pass here. */
export async function changePassword(currentPassword, newPassword) {
  const resp = await fetch("/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!resp.ok) {
    const data = await asJson(resp);
    throw new Error(data.detail || `HTTP ${resp.status}`);
  }
}

export async function fetchAdminConfig() {
  const resp = await fetch("/admin/config");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchFeedbackLog(hours = 168) {
  const resp = await fetch(`/admin/logs/feedback?hours=${encodeURIComponent(hours)}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchQueryTimingLog(hours = 24) {
  const resp = await fetch(`/admin/logs/queries?hours=${encodeURIComponent(hours)}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchEvalRuns() {
  const resp = await fetch("/admin/eval-runs");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchConversationCount() {
  const resp = await fetch("/conversations");
  if (!resp.ok) return 0;
  const data = await resp.json();
  return (data.conversations ?? []).filter((c) => (c.messages ?? []).length > 0).length;
}

/** Streams `/v1/chat/completions` (SSE) and calls `onDelta` with each text chunk. */
export async function askStreaming(query, onDelta) {
  const resp = await fetch("/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stream: true, messages: [{ role: "user", content: query }] }),
  });
  if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const events = buf.split("\n\n");
    buf = events.pop();
    for (const evt of events) {
      const line = evt.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (payload === "[DONE]") continue;
      const json = JSON.parse(payload);
      const delta = json.choices?.[0]?.delta?.content;
      if (delta) onDelta(delta);
    }
  }
}
