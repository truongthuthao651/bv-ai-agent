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

/** Streams one turn of POST /v1/chat/completions (SSE), calling `onDelta`
 *  with each text fragment as it arrives. `history` is the prior turns
 *  (in-memory only — see the Phase 4 gap list on persistence) so follow-up
 *  questions still get real conversational context within one page load.
 *  `signal` (an AbortController's) lets the caller cancel an in-flight
 *  generation — aborting the fetch closes the underlying connection, which
 *  Starlette's StreamingResponse detects as a client disconnect and stops
 *  the server-side generator (see CHAT-1, audit/REPORT.md). Throws the
 *  browser's standard AbortError on cancellation; the caller decides
 *  whether that's worth surfacing (it isn't — see ChatScreen.jsx's send()). */
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
