/** Thin fetch wrappers for the /chat UI. Deliberately separate from
 *  frontend/src/admin/api.js (small duplication of fetchMe/logout) so /chat
 *  and /admin stay independent bundles, matching the multi-page build. */

async function asJson(resp) {
  return resp.json().catch(() => ({}));
}

export async function fetchMe() {
  const resp = await fetch("/me");
  return asJson(resp);
}

export async function logout() {
  await fetch("/logout", { method: "POST" }).catch(() => {});
}

export async function fetchPromptSuggestions() {
  const resp = await fetch("/prompt-suggestions");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
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

/** Streams one turn of POST /v1/chat/completions (SSE), calling `onDelta`
 *  with each text fragment as it arrives. `history` is the prior turns
 *  (in-memory only — see the Phase 4 gap list on persistence) so follow-up
 *  questions still get real conversational context within one page load.
 *  `signal` (an AbortController's) lets the caller cancel an in-flight
 *  generation — aborting the fetch closes the underlying connection, which
 *  Starlette's StreamingResponse detects as a client disconnect and stops
 *  the server-side generator (see CHAT-1, audit/REPORT.md). Throws the
 *  browser's standard AbortError on cancellation; the caller decides
 *  whether that's worth surfacing (it isn't — see ChatScreen.jsx's send()).
 *  Returns the OpenAI-format completion id every SSE chunk of this answer
 *  carried (`chatcmpl-...`) — the caller can attach it to the message so a
 *  later thumbs-down (see sendFeedback below) can reference which answer. */
export async function askStreaming(messages, onDelta, signal) {
  const resp = await fetch("/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stream: true, messages }),
    signal,
  });
  if (!resp.ok || !resp.body) {
    const data = await asJson(resp);
    throw new Error(data.detail || `HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let completionId = null;
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
      if (json.id) completionId = json.id;
      const delta = json.choices?.[0]?.delta?.content;
      if (delta) onDelta(delta);
    }
  }
  return completionId;
}

/** P2-F2 (audit/REPORT.md): the only quality signal this app has in
 * production beyond eval/'s golden set — a thumbs-down on one streamed
 * answer, identified by its completion id. Deliberately metadata-only, no
 * query/answer text field exists to send here (matches the backend's
 * FeedbackRequest model and query_timing.py's established convention). */
export async function sendFeedback(completionId, reason) {
  const resp = await fetch("/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ completion_id: completionId, reason }),
  });
  if (!resp.ok) {
    const data = await asJson(resp);
    throw new Error(data.detail || `HTTP ${resp.status}`);
  }
}
