import { Modal } from "../components/index.js";
import { DocumentUploadForm } from "../documents/DocumentUploadForm.jsx";
import { UPLOAD_HINT } from "../documents/documentUploadOptions.js";

/** Admin-only upload dialog from the chat screen. */
export function DocumentUploadModal({ open, onClose }) {
  return (
    <Modal open={open} title="Nạp tài liệu" hint={UPLOAD_HINT} onClose={onClose}>
      <DocumentUploadForm onSuccess={() => setTimeout(onClose, 1200)} />
    </Modal>
  );
}
