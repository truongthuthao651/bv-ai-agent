import { useEffect, useState } from "react";
import { Card, Input, Select, Button, Table, Tag, Modal } from "../components/index.js";
import { DocumentUploadForm } from "../documents/DocumentUploadForm.jsx";
import { UPLOAD_HINT } from "../documents/documentUploadOptions.js";
import { departmentDisplay, departmentOptionLabel } from "./departmentLabels.js";
import { fetchDocuments, updateDocument, deleteDocument } from "./api.js";

const EDIT_DOC_TYPE_OPTIONS = [
  { value: "policy", label: "policy — Hợp đồng / Quy tắc bảo hiểm" },
  { value: "procedure", label: "procedure — Quy trình" },
  { value: "form", label: "form — Biểu mẫu" },
  { value: "spreadsheet", label: "spreadsheet — Bảng tính" },
  { value: "image", label: "image — Hình ảnh scan" },
  { value: "figure", label: "figure — Hình vẽ / biểu đồ" },
  { value: "glossary", label: "glossary — Từ điển thuật ngữ" },
  { value: "reference", label: "reference — Tham khảo công khai" },
  { value: "other", label: "other — Khác" },
];

// P2-T2 (audit/REPORT.md): doc_type was shown as the raw English enum value
// ("policy", "other", ...) in every table/chart, even though the upload and
// edit dropdowns are already bilingual (EDIT_DOC_TYPE_OPTIONS above) — an
// admin picks a Vietnamese-labeled option, then sees the bare English code
// reflected back in every table and chart afterward. One shared lookup,
// exported so OverviewView.jsx's recent-documents list uses the same labels
// instead of its own copy drifting out of sync.
export const DOC_TYPE_LABEL = Object.fromEntries(
  EDIT_DOC_TYPE_OPTIONS.map((o) => [o.value, o.label.split(" — ")[1]]),
);

const DEPARTMENTS = ["PTSP", "DP", "DVA"];

function UploadCard({ onUploaded }) {
  return (
    <Card title="Nạp tài liệu" hint={UPLOAD_HINT}>
      <DocumentUploadForm onUploaded={onUploaded} />
    </Card>
  );
}

function EditModal({ doc, onClose, onSaved }) {
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
      setStatus({ text: "Tên tài liệu không được để trống.", tone: "bad" });
      return;
    }
    setBusy(true);
    setStatus(renaming ? { text: "Đang nạp lại tài liệu với tên mới… (có thể mất một lúc)", tone: "warn" } : { text: "Đang lưu…", tone: "" });
    try {
      await updateDocument(doc.doc_id, { doc_title: newTitle, doc_type: docType, department, source_url: sourceUrl.trim() });
      onSaved();
    } catch (err) {
      setStatus({ text: "Lỗi: " + err.message, tone: "bad" });
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
      title="Sửa tài liệu"
      hint="Chỉnh sửa tên, loại, phòng ban và nguồn công khai của tài liệu."
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Huỷ
          </Button>
          <Button onClick={save} disabled={busy}>
            Lưu
          </Button>
        </>
      }
    >
      <div onKeyDown={onFieldKeyDown} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>Tên tài liệu</label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          {renaming && (
            <p style={{ margin: "var(--space-2) 0 0", fontSize: "var(--text-2xs)", color: "var(--warning)" }}>
              ⚠️ Đổi tên sẽ nạp lại tài liệu từ tệp gốc để tìm kiếm bám đúng tên mới — có thể mất một lúc (do enrichment công thức).
            </p>
          )}
        </div>
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>Loại tài liệu</label>
          <Select value={docType} onChange={(e) => setDocType(e.target.value)} style={{ width: "100%" }}>
            {EDIT_DOC_TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>Nguồn URL công khai</label>
          <Input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://… (để trống nếu là tài liệu nội bộ)" />
          <p style={{ margin: "var(--space-2) 0 0", fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>
            Chỉ dùng cho tài liệu công khai. Trích dẫn sẽ trỏ thẳng tới địa chỉ này và được gắn nhãn "nguồn công khai"; ứng dụng không bao giờ tự truy cập nó.
          </p>
        </div>
        <div>
          <label style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", marginBottom: "var(--space-1)" }}>Phòng ban</label>
          <Select value={department} onChange={(e) => setDepartment(e.target.value)} style={{ width: "100%" }}>
            <option value="">(không đặt)</option>
            {DEPARTMENTS.map((d) => (
            <option key={d} value={d}>
              {departmentOptionLabel(d)}
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
          (DOC_TYPE_LABEL[d.doc_type] || d.doc_type).toLowerCase().includes(query) ||
          (d.department || "").toLowerCase().includes(query),
      )
    : docs;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
      <div>
        <h1 style={{ fontSize: "var(--text-3xl)", fontWeight: "var(--weight-heavy)", letterSpacing: "var(--tracking-tight)", color: "var(--text-primary)", margin: "0 0 var(--space-2)", lineHeight: "var(--leading-tight)" }}>
          Tài liệu
        </h1>
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "var(--text-md)" }}>Nạp, gắn nhãn và theo dõi các tài liệu trợ lý có thể tìm kiếm.</p>
      </div>

      {canManage ? (
        <UploadCard onUploaded={load} />
      ) : (
        <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
          Tài khoản nhân viên chỉ xem được danh sách tài liệu — nạp/sửa/xoá cần tài khoản quản trị viên.
        </p>
      )}

      <Card
        title="Tài liệu đã nạp"
        hint={
          loadError
            ? `Không tải được danh sách: ${loadError}`
            : query
              ? `${filteredDocs.length}/${docs.length} tài liệu phù hợp · ${totalChunks} đoạn`
              : `${docs.length} tài liệu · ${totalChunks} đoạn`
        }
        size="lg"
      >
        {docs.length > 0 && (
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Tìm theo tên, loại hoặc phòng ban…"
            style={{ width: "100%", maxWidth: 360, marginBottom: "var(--space-4)" }}
          />
        )}
        <Table
          columns={canManage ? ["Tên tài liệu", "Loại", "Phòng ban", "Số đoạn", "Thời gian nạp", ""] : ["Tên tài liệu", "Loại", "Phòng ban", "Số đoạn", "Thời gian nạp"]}
          rows={filteredDocs}
          emptyLabel={query ? "Không có tài liệu nào khớp." : "Chưa có tài liệu nào được nạp."}
          renderRow={(d) => {
            const cells = [
              <div key="title" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap" }}>
                <a
                  href={`/documents/${encodeURIComponent(d.doc_id)}/view`}
                  target="_blank"
                  rel="noopener"
                  title="Xem tài liệu"
                  style={{ color: "var(--accent)", fontWeight: "var(--weight-semibold)" }}
                >
                  {d.doc_title}
                </a>
                {d.source_url && <Tag tone="muted">nguồn công khai</Tag>}
              </div>,
              <Tag key="type">{DOC_TYPE_LABEL[d.doc_type] || d.doc_type}</Tag>,
              departmentDisplay(d.department),
              d.n_chunks,
              d.ingested_at ? new Date(d.ingested_at).toLocaleString("vi-VN") : "—",
            ];
            if (canManage) {
              cells.push(
                <div key="actions" style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end" }}>
                  <Button size="sm" variant="secondary" onClick={() => setEditingDoc(d)}>
                    Sửa
                  </Button>
                  <Button size="sm" variant="danger" disabled={deletingId === d.doc_id} onClick={() => setConfirmDeleteDoc(d)}>
                    Xoá
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
          title="Xoá tài liệu?"
          hint={`Xoá tài liệu "${confirmDeleteDoc.doc_title}" khỏi hệ thống? Thao tác này không thể hoàn tác.`}
          onClose={closeDeleteConfirm}
          actions={
            <>
              <Button variant="secondary" onClick={closeDeleteConfirm} disabled={deletingId === confirmDeleteDoc.doc_id}>
                Huỷ
              </Button>
              <Button variant="danger" onClick={confirmDelete} disabled={deletingId === confirmDeleteDoc.doc_id}>
                Xoá
              </Button>
            </>
          }
        >
          {deleteError && <div style={{ fontSize: "var(--text-xs)", color: "var(--danger)" }}>Lỗi: {deleteError}</div>}
        </Modal>
      )}
    </div>
  );
}
