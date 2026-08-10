import { useEffect, useState } from "react";
import { Card, Input, Select, Button, Table, Tag, Modal, Icon } from "../components/index.js";
import { DocumentUploadForm } from "../documents/DocumentUploadForm.jsx";
import {
  editDocTypeOptions,
  docTypeLabel,
  localizedDepartmentDisplay,
  localizedDepartmentOption,
} from "../i18n/catalog.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { fetchDocuments, updateDocument, deleteDocument } from "./api.js";
import { formatVnDateTime } from "./formatVnTime.js";

const DEPARTMENTS = ["PTSP", "DP", "DVA"];

export function docTypeLabelForOverview(value, t) {
  return docTypeLabel(value, t);
}

function UploadCard({ onUploaded }) {
  const { t } = useLocale();
  return (
    <Card title={t("upload.title")} hint={t("upload.hint")}>
      <DocumentUploadForm onUploaded={onUploaded} />
    </Card>
  );
}

function EditModal({ doc, onClose, onSaved }) {
  const { t } = useLocale();
  const [title, setTitle] = useState(doc.doc_title);
  const [docType, setDocType] = useState(doc.doc_type);
  const [department, setDepartment] = useState(doc.department || "");
  const [sourceUrl, setSourceUrl] = useState(doc.source_url || "");
  const [status, setStatus] = useState({ text: "", tone: "" });
  const [busy, setBusy] = useState(false);

  const renaming = title.trim() !== doc.doc_title;

  async function save() {
    const newTitle = title.trim();
    if (!newTitle) {
      setStatus({ text: t("documents.titleRequired"), tone: "bad" });
      return;
    }
    setBusy(true);
    setStatus(renaming ? { text: t("documents.reingesting"), tone: "warn" } : { text: t("common.saving"), tone: "" });
    try {
      await updateDocument(doc.doc_id, { doc_title: newTitle, doc_type: docType, department, source_url: sourceUrl.trim() });
      onSaved();
    } catch (err) {
      setStatus({ text: `${t("common.error")}: ${err.message}`, tone: "bad" });
    } finally {
      setBusy(false);
    }
  }

  const toneColor = { ok: "var(--success)", bad: "var(--danger)", warn: "var(--warning)", "": "var(--text-secondary)" }[status.tone];

  // P2-C2 (audit/REPORT.md): Enter submits everywhere else in the app
  // (Composer, the Overview quick-ask panel) but not here — one handler on
  // the form's own text inputs, same IME-safe guard as those. Excludes
  // <select> so its own native Enter/keyboard behavior isn't hijacked.
  function onFieldKeyDown(e) {
    if (e.key === "Enter" && !e.nativeEvent.isComposing && e.target.tagName !== "SELECT") {
      e.preventDefault();
      if (!busy) save();
    }
  }

  return (
    <Modal
      open
      title={t("documents.editTitle")}
      hint={t("documents.editHint")}
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={busy}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div onKeyDown={onFieldKeyDown} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>{t("documents.docTitleLabel")}</label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          {renaming && (
            <p style={{ margin: "var(--space-2) 0 0", display: "flex", alignItems: "flex-start", gap: "var(--space-2)", fontSize: "var(--text-2xs)", color: "var(--warning)" }}>
              <Icon name="alert-triangle" size={14} style={{ marginTop: 1, flexShrink: 0 }} />
              <span>{t("documents.renameWarning")}</span>
            </p>
          )}
        </div>
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>{t("documents.docTypeLabel")}</label>
          <Select value={docType} onChange={(e) => setDocType(e.target.value)} style={{ width: "100%" }}>
            {editDocTypeOptions(t).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>{t("documents.sourceUrlLabel")}</label>
          <Input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder={t("documents.sourceUrlPlaceholder")} />
          <p style={{ margin: "var(--space-2) 0 0", fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>
            {t("documents.sourceUrlHint")}
          </p>
        </div>
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>{t("documents.deptLabel")}</label>
          <Select value={department} onChange={(e) => setDepartment(e.target.value)} style={{ width: "100%" }}>
            <option value="">{t("common.unset")}</option>
            {DEPARTMENTS.map((d) => (
            <option key={d} value={d}>
              {localizedDepartmentOption(d, t)}
            </option>
            ))}
          </Select>
        </div>
        {status.text && <div style={{ fontSize: "var(--text-xs)", color: toneColor }}>{status.text}</div>}
      </div>
    </Modal>
  );
}

export function DocumentsView({ canManage = true }) {
  const { t } = useLocale();
  const [docs, setDocs] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [editingDoc, setEditingDoc] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [confirmDeleteDoc, setConfirmDeleteDoc] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [search, setSearch] = useState("");

  async function load() {
    try {
      const data = await fetchDocuments();
      setDocs(data);
      setLoadError(null);
    } catch (err) {
      setLoadError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function closeDeleteConfirm() {
    setConfirmDeleteDoc(null);
    setDeleteError(null);
  }

  // P2-C1 (audit/REPORT.md): this used to be window.confirm/window.alert —
  // native dialogs render outside the app's theme (light/dark, brand colors),
  // freeze the tab while shown, and look like nothing else in the product.
  // The app already has a themed Modal (used two lines away for Edit) and a
  // Button variant="danger" (used on the row's own "Xoá" button) — this is a
  // drop-in swap onto both, not a new pattern.
  async function confirmDelete() {
    const doc = confirmDeleteDoc;
    if (!doc) return;
    setDeletingId(doc.doc_id);
    setDeleteError(null);
    try {
      await deleteDocument(doc.doc_id);
      setConfirmDeleteDoc(null);
      load();
    } catch (err) {
      setDeleteError(err.message);
    } finally {
      setDeletingId(null);
    }
  }

  const totalChunks = docs.reduce((sum, d) => sum + d.n_chunks, 0);

  // P2-F3 (audit/REPORT.md): no search/filter existed at all — fine at the
  // handful of synthetic documents today, a real problem once a department's
  // real corpus grows past a page. GET /documents already fetches the whole
  // list in one call with no server-side pagination, so a client-side filter
  // is the cheap fix that works up to a few hundred rows; server-side
  // pagination is a separate, larger change to make only once the corpus
  // actually approaches that scale (not yet).
  const query = search.trim().toLowerCase();
  const filteredDocs = query
    ? docs.filter(
        (d) =>
          d.doc_title.toLowerCase().includes(query) ||
          docTypeLabel(d.doc_type, t).toLowerCase().includes(query) ||
          (d.department || "").toLowerCase().includes(query),
      )
    : docs;

  const tableColumns = canManage
    ? [t("documents.colTitle"), t("documents.colType"), t("documents.colDept"), t("documents.colChunks"), t("documents.colIngested"), ""]
    : [t("documents.colTitle"), t("documents.colType"), t("documents.colDept"), t("documents.colChunks"), t("documents.colIngested")];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
      <div>
        <h1 style={{ fontSize: "var(--text-3xl)", fontWeight: "var(--weight-heavy)", letterSpacing: "var(--tracking-tight)", color: "var(--text-primary)", margin: "0 0 var(--space-2)", lineHeight: "var(--leading-tight)" }}>
          {t("documents.title")}
        </h1>
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "var(--text-md)" }}>{t("documents.pageDescription")}</p>
      </div>

      {canManage ? (
        <UploadCard onUploaded={load} />
      ) : (
        <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
          {t("documents.employeeNote")}
        </p>
      )}

      <Card
        title={t("documents.ingestedList")}
        hint={
          loadError
            ? `${t("admin.loadListError")} ${loadError}`
            : query
              ? t("documents.listSummaryFiltered", { filtered: filteredDocs.length, total: docs.length, chunks: totalChunks })
              : t("documents.listSummary", { count: docs.length, chunks: totalChunks })
        }
        size="lg"
      >
        {docs.length > 0 && (
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("documents.searchPlaceholder")}
            style={{ width: "100%", maxWidth: 360, marginBottom: "var(--space-4)" }}
          />
        )}
        <Table
          columns={tableColumns}
          rows={filteredDocs}
          emptyLabel={query ? t("documents.noMatch") : t("documents.empty")}
          renderRow={(d) => {
            const cells = [
              <div key="title" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap" }}>
                <a
                  href={`/documents/${encodeURIComponent(d.doc_id)}/view`}
                  target="_blank"
                  rel="noopener"
                  title={t("documents.viewDocument")}
                  style={{ color: "var(--accent)", fontWeight: "var(--weight-semibold)" }}
                >
                  {d.doc_title}
                </a>
                {d.source_url && <Tag tone="muted">{t("documents.publicSource")}</Tag>}
              </div>,
              <Tag key="type">{docTypeLabel(d.doc_type, t)}</Tag>,
              localizedDepartmentDisplay(d.department, t),
              d.n_chunks,
              formatVnDateTime(d.ingested_at),
            ];
            if (canManage) {
              cells.push(
                <div key="actions" style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end" }}>
                  <Button size="sm" variant="secondary" onClick={() => setEditingDoc(d)}>
                    {t("common.edit")}
                  </Button>
                  <Button size="sm" variant="danger" disabled={deletingId === d.doc_id} onClick={() => setConfirmDeleteDoc(d)}>
                    {t("common.delete")}
                  </Button>
                </div>,
              );
            }
            return cells;
          }}
        />
      </Card>

      {canManage && editingDoc && (
        <EditModal
          doc={editingDoc}
          onClose={() => setEditingDoc(null)}
          onSaved={() => {
            setEditingDoc(null);
            load();
          }}
        />
      )}

      {canManage && confirmDeleteDoc && (
        <Modal
          open
          title={t("documents.deleteTitle")}
          hint={t("documents.deleteHint", { title: confirmDeleteDoc.doc_title })}
          onClose={closeDeleteConfirm}
          actions={
            <>
              <Button variant="secondary" onClick={closeDeleteConfirm} disabled={deletingId === confirmDeleteDoc.doc_id}>
                {t("common.cancel")}
              </Button>
              <Button variant="danger" onClick={confirmDelete} disabled={deletingId === confirmDeleteDoc.doc_id}>
                {t("common.delete")}
              </Button>
            </>
          }
        >
          {deleteError && <div style={{ fontSize: "var(--text-xs)", color: "var(--danger)" }}>{t("common.error")}: {deleteError}</div>}
        </Modal>
      )}
    </div>
  );
}
