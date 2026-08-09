import { useRef, useState } from "react";
import { Button, Dropzone, Input, Select } from "../components/index.js";
import { departmentOptionLabel } from "../admin/departmentLabels.js";
import { DOC_TYPE_OPTIONS, UPLOAD_ACCEPT, UPLOAD_DEPARTMENTS } from "./documentUploadOptions.js";
import { uploadDocument } from "./uploadApi.js";

/** Admin document upload form — shared by /admin Documents and /chat modal. */
export function DocumentUploadForm({ onUploaded, onSuccess }) {
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
      const summary =
        `Đã nạp "${data.doc_title}" (${data.doc_type}) — ${data.n_chunks} đoạn` +
        (data.n_figures ? `, ${data.n_figures} hình` : "") +
        ".";
      setStatus(
        data.title_warning
          ? { text: summary + "\n⚠️ " + data.title_warning, tone: "warn" }
          : { text: summary, tone: "ok" },
      );
      setFile(null);
      setDocTitle("");
      setSourceUrl("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      onUploaded?.();
      onSuccess?.(data);
    } catch (err) {
      setStatus({ text: "Lỗi: " + err.message, tone: "bad" });
    } finally {
      setBusy(false);
    }
  }

  const toneColor = { ok: "var(--success)", bad: "var(--danger)", warn: "var(--warning)", "": "var(--text-muted)" }[status.tone];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <Dropzone
        label={file ? file.name : "Kéo thả tệp vào đây, hoặc bấm để chọn"}
        hint=".md · .docx · .xlsx · .pdf · .yaml · .yml"
        dragging={dragging}
        onClick={() => fileInputRef.current?.click()}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
        }}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept={UPLOAD_ACCEPT}
        style={{ display: "none" }}
        onChange={(e) => setFile(e.target.files[0] || null)}
      />
      <Input
        value={docTitle}
        onChange={(e) => setDocTitle(e.target.value)}
        placeholder="Tên tài liệu (tuỳ chọn — nên ghi kèm tên sản phẩm)"
      />
      <Input
        value={sourceUrl}
        onChange={(e) => setSourceUrl(e.target.value)}
        placeholder="Nguồn URL công khai (tuỳ chọn — chỉ cho tài liệu công khai)"
      />
      <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <Select value={docType} onChange={(e) => setDocType(e.target.value)} style={{ flex: 1, minWidth: 220 }}>
          {DOC_TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
        <Select value={department} onChange={(e) => setDepartment(e.target.value)} style={{ minWidth: 180 }}>
          <option value="">Phòng ban: (không đặt)</option>
          {UPLOAD_DEPARTMENTS.map((d) => (
            <option key={d} value={d}>
              {departmentOptionLabel(d)}
            </option>
          ))}
        </Select>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <Button onClick={submit} disabled={busy}>
          {busy ? "Đang nạp…" : "Nạp tài liệu"}
        </Button>
      </div>
      {status.text && (
        <div style={{ fontSize: "var(--text-xs)", color: toneColor, whiteSpace: "pre-wrap" }}>{status.text}</div>
      )}
    </div>
  );
}
