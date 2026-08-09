import { useRef, useState } from "react";
import { Button, Dropzone, Icon, Input, Select } from "../components/index.js";
import { docTypeOptions, localizedDepartmentOption } from "../i18n/catalog.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { UPLOAD_ACCEPT, UPLOAD_DEPARTMENTS } from "./documentUploadOptions.js";
import { uploadDocument } from "./uploadApi.js";

/** Admin document upload form — shared by /admin Documents and /chat modal. */
export function DocumentUploadForm({ onUploaded, onSuccess }) {
  const { t } = useLocale();
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [docTitle, setDocTitle] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [docType, setDocType] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState({ text: "", tone: "" });
  const [busy, setBusy] = useState(false);
  const typeOptions = docTypeOptions(t);

  async function submit() {
    if (!file) {
      setStatus({ text: t("upload.pickFile"), tone: "bad" });
      return;
    }
    setBusy(true);
    setStatus({ text: t("upload.uploadingFile", { name: file.name }), tone: "" });
    try {
      const data = await uploadDocument({ file, docType, department, docTitle, sourceUrl });
      const figures = data.n_figures ? t("upload.withFigures", { n: data.n_figures }) : "";
      const summary = t("upload.uploaded", {
        title: data.doc_title,
        type: data.doc_type,
        chunks: data.n_chunks,
        figures,
      });
      setStatus(
        data.title_warning
          ? { text: summary, tone: "warn", warning: data.title_warning }
          : { text: summary, tone: "ok" },
      );
      setFile(null);
      setDocTitle("");
      setSourceUrl("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      onUploaded?.();
      onSuccess?.(data);
    } catch (err) {
      setStatus({ text: `${t("common.error")}: ${err.message}`, tone: "bad" });
    } finally {
      setBusy(false);
    }
  }

  const toneColor = { ok: "var(--success)", bad: "var(--danger)", warn: "var(--warning)", "": "var(--text-muted)" }[status.tone];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <Dropzone
        label={file ? file.name : t("upload.dropzone")}
        hint={t("upload.dropzoneHint")}
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
      <Input value={docTitle} onChange={(e) => setDocTitle(e.target.value)} placeholder={t("upload.docTitlePlaceholder")} />
      <Input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder={t("upload.sourceUrlPlaceholder")} />
      <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <Select value={docType} onChange={(e) => setDocType(e.target.value)} style={{ flex: 1, minWidth: 220 }}>
          {typeOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
        <Select value={department} onChange={(e) => setDepartment(e.target.value)} style={{ minWidth: 180 }}>
          <option value="">{t("upload.deptUnset")}</option>
          {UPLOAD_DEPARTMENTS.map((d) => (
            <option key={d} value={d}>
              {localizedDepartmentOption(d, t)}
            </option>
          ))}
        </Select>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <Button onClick={submit} disabled={busy}>
          {busy ? t("upload.uploading") : t("upload.uploadButton")}
        </Button>
      </div>
      {status.text && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          <div style={{ fontSize: "var(--text-xs)", color: toneColor }}>{status.text}</div>
          {status.warning && (
            <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-2)", fontSize: "var(--text-xs)", color: "var(--warning)" }}>
              <Icon name="alert-triangle" size={14} style={{ marginTop: 1, flexShrink: 0 }} />
              <span>{status.warning}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
