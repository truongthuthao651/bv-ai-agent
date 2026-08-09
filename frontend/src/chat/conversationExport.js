/** Export conversations to downloadable files. */

function downloadBlob(filename, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function safeFilename(label) {
  return (label || "cuoc-tro-chuyen")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 60)
    .replace(/^-|-$/g, "") || "cuoc-tro-chuyen";
}

export function exportConversationMarkdown(conv) {
  const lines = [`# ${conv.title || "Cuộc trò chuyện"}\n`];
  for (const m of conv.messages ?? []) {
    if (m.role === "user") lines.push(`## Bạn\n\n${m.text}\n`);
    else if (m.text) lines.push(`## Trợ lý\n\n${m.text}\n`);
  }
  const stamp = new Date().toISOString().slice(0, 10);
  downloadBlob(`${safeFilename(conv.title)}-${stamp}.md`, lines.join("\n"), "text/markdown;charset=utf-8");
}

export function exportConversationJson(conv) {
  const stamp = new Date().toISOString().slice(0, 10);
  downloadBlob(
    `${safeFilename(conv.title)}-${stamp}.json`,
    JSON.stringify(conv, null, 2),
    "application/json;charset=utf-8",
  );
}

export function exportAllConversationsJson(conversations) {
  const stamp = new Date().toISOString().slice(0, 10);
  downloadBlob(
    `bv-conversations-${stamp}.json`,
    JSON.stringify({ exported_at: new Date().toISOString(), conversations }, null, 2),
    "application/json;charset=utf-8",
  );
}
