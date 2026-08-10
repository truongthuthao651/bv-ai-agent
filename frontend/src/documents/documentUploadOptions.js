/** Shared upload dropdown options — used by admin Documents and chat upload. */

export const DOC_TYPE_OPTIONS = [
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

export const UPLOAD_DEPARTMENTS = ["PTSP", "DP", "DVA"]; // match settings.departments

export const UPLOAD_ACCEPT = ".md,.docx,.yaml,.yml,.pdf,.xlsx,.xls,.png,.jpg,.jpeg";

export const UPLOAD_HINT =
  "Hỗ trợ: Markdown (.md), Word (.docx), Excel (.xlsx), PDF (có lớp chữ), từ điển (.yaml/.yml). PDF scan / hình ảnh đang phát triển.";
