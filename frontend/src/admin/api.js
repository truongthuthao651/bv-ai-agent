/** Thin fetch wrappers over the real FastAPI admin endpoints. No new behavior
 *  beyond what app/static/index.html already did — same paths, same methods,
 *  same error shapes — just called from React instead of vanilla JS. */

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

export async function uploadDocument({ file, docType, department, docTitle, sourceUrl }) {
  const fd = new FormData();
  fd.append("file", file);
  if (docType) fd.append("doc_type", docType);
  if (department) fd.append("department", department);
  if (docTitle) fd.append("doc_title", docTitle);
  if (sourceUrl) fd.append("source_url", sourceUrl);
  const resp = await fetch("/ingest", { method: "POST", body: fd });
  const data = await asJson(resp);
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

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

/** Streams `/v1/chat/completions` (SSE) and calls `onDelta` with each text
 *  fragment as it arrives — the same parsing app/static/index.html did. */
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
