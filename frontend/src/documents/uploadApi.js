/** POST /ingest — admin-only document upload (shared by admin UI and chat). */

async function asJson(resp) {
  return resp.json().catch(() => ({}));
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
