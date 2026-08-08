import { useEffect, useRef, useState } from "react";
import { Card, Dropzone, Input, Select, Button, Table, Tag, Modal } from "../components/index.js";
import { fetchDocuments, uploadDocument, updateDocument, deleteDocument } from "./api.js";

const DOC_TYPE_OPTIONS = [
  { value: "", label: "Loại tài liệu: tự động theo phần mở rộng" },
  { value: "policy", label: "Hợp đồng / Quy tắc bảo hiểm (policy)" },
  { value: "procedure", label: "Quy trình (procedure)" },
  { value: "form", label: "Biểu mẫu (form)" },
  { value: "spreadsheet", label: "Bảng tính (spreadsheet)" },
  { value: "image", label: "Hình ảnh scan (image)" },
  { value: "figure", label: "Hình vẽ / biểu đồ (figure)" },
  { value: "glossary", label: "Từ điển thuật ngữ (glossary)" },
  { value: "reference", label: "Tham khảo công khai (reference)" },
  { value: "other", label: "Khác (other)" },
];

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

// Options mirror settings.departments (source of truth for validation).
const DEPARTMENTS = ["PTSP", "DP", "DVA"];

function UploadCard({ onUploaded }) {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [docTitle, setDocTitle] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [docType, setDocType] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState({ text: "", tone: "" });
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!file) {
      setStatus({ text: "Chọn một tệp trước.", tone: "bad" });
      return;
    }
    setBusy(true);
    setStatus({ text: `Đang nạp "${file.name}"… (có thể mất một lúc do enrichment công thức)`, tone: "" });
    try {
      const data = await uploadDocument({ file, docType, department, docTitle, sourceUrl });
      const summary = `Đã nạp "${data.doc_title}" (${data.doc_type}) — ${data.n_chunks} đoạn` + (data.n_figures ? `, ${data.n_figures} hình` : "") + ".";
      setStatus(data.title_warning ? { text: summary + "\n⚠️ " + data.title_warning, tone: "warn" } : { text: summary, tone: "ok" });
      setFile(null);
      setDocTitle("");
      setSourceUrl("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      onUploaded();
    } catch (err) {
      setStatus({ text: "Lỗi: " + err.message, tone: "bad" });
    } finally {
      setBusy(false);
    }
  }

  const toneColor = { ok: "var(--success)", bad: "var(--danger)", warn: "var(--warning)", "": "var(--text-muted)" }[status.tone];

  return (
    <Card title="Nạp tài liệu" hint="Hỗ trợ hiện tại: Markdown (.md), Word (.docx), Excel (.xlsx), PDF (có lớp chữ), từ điển thuật ngữ (.yaml/.yml). PDF scan / hình ảnh đang được phát triển (sẽ báo lỗi rõ ràng nếu chọn nhầm).">
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        <Dropzone
          label={file ? file.name : "Kéo thả tệp vào đây, hoặc bấm để chọn"}
          hint=".md · .docx · .xlsx · .pdf · .yaml · .yml"
          dragging={dragging}
          onClick={() => fileInputRef.current?.click()}
          onDragEnter={(e) => { e.preventDefault(); setDragging(true); }}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={(e) => { e.preventDefault(); setDragging(false); }}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
          }}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".md,.docx,.yaml,.yml,.pdf,.xlsx,.xls,.png,.jpg,.jpeg"
          style={{ display: "none" }}
          onChange={(e) => setFile(e.target.files[0] || null)}
        />
        <Input value={docTitle} onChange={(e) => setDocTitle(e.target.value)} placeholder="Tên tài liệu (tuỳ chọn — ghi đè tên tự trích từ file, nên ghi kèm tên sản phẩm)" />
        {/* Knowledge pack: chỉ điền cho tài liệu CÔNG KHAI. Địa chỉ này không bao giờ được ứng dụng truy cập, chỉ dùng làm liên kết trích dẫn. */}
        <Input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="Nguồn URL công khai (tuỳ chọn — chỉ cho tài liệu công khai; trích dẫn sẽ trỏ tới địa chỉ này)" />
        <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <Select value={docType} onChange={(e) => setDocType(e.target.value)} style={{ flex: 1, minWidth: 260 }}>
            {DOC_TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <Select value={department} onChange={(e) => setDepartment(e.target.value)}>
            <option value="">Phòng ban: (không đặt)</option>
            {DEPARTMENTS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </Select>
          <Button onClick={submit} disabled={busy}>
            Nạp tài liệu
          </Button>
        </div>
        {status.text && <div style={{ fontSize: "var(--text-xs)", color: toneColor, whiteSpace: "pre-wrap" }}>{status.text}</div>}
      </div>
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
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
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
                {d}
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

  async function handleDelete(doc) {
    if (!window.confirm(`Xoá tài liệu "${doc.doc_title}" khỏi hệ thống? Thao tác này không thể hoàn tác.`)) return;
    setDeletingId(doc.doc_id);
    try {
      await deleteDocument(doc.doc_id);
      load();
    } catch (err) {
      window.alert("Không xoá được: " + err.message);
    } finally {
      setDeletingId(null);
    }
  }

  const totalChunks = docs.reduce((sum, d) => sum + d.n_chunks, 0);

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
        hint={loadError ? `Không tải được danh sách: ${loadError}` : `${docs.length} tài liệu · ${totalChunks} đoạn`}
        size="lg"
      >
        <Table
          columns={canManage ? ["Tên tài liệu", "Loại", "Phòng ban", "Số đoạn", "Thời gian nạp", ""] : ["Tên tài liệu", "Loại", "Phòng ban", "Số đoạn", "Thời gian nạp"]}
          rows={docs}
          emptyLabel="Chưa có tài liệu nào được nạp."
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
              <Tag key="type">{d.doc_type}</Tag>,
              d.department || "—",
              d.n_chunks,
              d.ingested_at ? new Date(d.ingested_at).toLocaleString("vi-VN") : "—",
            ];
            if (canManage) {
              cells.push(
                <div key="actions" style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end" }}>
                  <Button size="sm" variant="secondary" onClick={() => setEditingDoc(d)}>
                    Sửa
                  </Button>
                  <Button size="sm" variant="danger" disabled={deletingId === d.doc_id} onClick={() => handleDelete(d)}>
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
    </div>
  );
}
