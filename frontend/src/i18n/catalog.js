import { translate } from "./messages.js";

const LEGACY_NEW_CHAT = new Set(["Cuộc trò chuyện mới", "New conversation"]);

export function localizedRoleLabel(role, t) {
  if (role === "admin") return t("user.roleAdmin");
  if (role === "employee") return t("user.roleEmployee");
  return role ?? "";
}

export function localizedDepartmentLabel(code, t) {
  if (!code) return "—";
  const key = `dept.${code}`;
  const label = t(key);
  return label === key ? code : label;
}

export function localizedDepartmentOption(code, t) {
  const label = localizedDepartmentLabel(code, t);
  return label === "—" ? code : `${code} — ${label}`;
}

export function localizedDepartmentDisplay(code, t) {
  if (!code) return "—";
  return `${code} — ${localizedDepartmentLabel(code, t)}`;
}

export function docTypeOptions(t) {
  return [
    { value: "", label: t("upload.docTypeAuto") },
    { value: "policy", label: t("upload.docTypePolicy") },
    { value: "procedure", label: t("upload.docTypeProcedure") },
    { value: "form", label: t("upload.docTypeForm") },
    { value: "spreadsheet", label: t("upload.docTypeSpreadsheet") },
    { value: "image", label: t("upload.docTypeImage") },
    { value: "figure", label: t("upload.docTypeFigure") },
    { value: "glossary", label: t("upload.docTypeGlossary") },
    { value: "reference", label: t("upload.docTypeReference") },
    { value: "other", label: t("upload.docTypeOther") },
  ];
}

export function editDocTypeOptions(t) {
  return [
    { value: "policy", label: t("upload.editPolicy") },
    { value: "procedure", label: t("upload.editProcedure") },
    { value: "form", label: t("upload.editForm") },
    { value: "spreadsheet", label: t("upload.editSpreadsheet") },
    { value: "image", label: t("upload.editImage") },
    { value: "figure", label: t("upload.editFigure") },
    { value: "glossary", label: t("upload.editGlossary") },
    { value: "reference", label: t("upload.editReference") },
    { value: "other", label: t("upload.editOther") },
  ];
}

export function docTypeLabel(value, t) {
  const opt = editDocTypeOptions(t).find((o) => o.value === value);
  if (!opt) return value;
  const parts = opt.label.split(" — ");
  return parts.length > 1 ? parts[1] : opt.label;
}

export function localizedConversationLabel(conv, t, deriveTitleFn) {
  if (conv.customTitle) return conv.customTitle;
  const messages = conv.messages ?? [];
  if (messages.length === 0) return t("chat.newChat");
  if (conv.title && !LEGACY_NEW_CHAT.has(conv.title)) return conv.title;
  return deriveTitleFn ? deriveTitleFn(messages, t("chat.newChat")) : t("chat.newChat");
}

export function localizedGroupConversationsByDate(conversations, t) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;
  const sorted = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);
  const today = [];
  const yesterday = [];
  const older = [];
  for (const conv of sorted) {
    if (conv.updatedAt >= startOfToday) today.push(conv);
    else if (conv.updatedAt >= startOfYesterday) yesterday.push(conv);
    else older.push(conv);
  }
  const groups = [];
  if (today.length) groups.push({ title: t("chat.groupToday"), items: today });
  if (yesterday.length) groups.push({ title: t("chat.groupYesterday"), items: yesterday });
  if (older.length) groups.push({ title: t("chat.groupOlder"), items: older });
  return groups;
}

export function refusalTexts(locale) {
  return [
    translate(locale, "chat.refusalExact"),
    translate("vi", "chat.refusalExact"),
  ];
}

export function isRefusalAnswer(text, locale) {
  const cleaned = text.replace(/\n\n_⏱[^_]*_\s*$/, "").trim();
  return refusalTexts(locale).some((r) => cleaned === r);
}
