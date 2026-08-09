import { Modal } from "../components/index.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { DocumentUploadForm } from "../documents/DocumentUploadForm.jsx";

/** Admin-only upload dialog from the chat screen. */
export function DocumentUploadModal({ open, onClose }) {
  const { t } = useLocale();
  return (
    <Modal open={open} title={t("upload.title")} hint={t("upload.hint")} onClose={onClose}>
      <DocumentUploadForm onSuccess={() => setTimeout(onClose, 1200)} />
    </Modal>
  );
}
