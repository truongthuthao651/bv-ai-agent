/** Client-side profile preferences — keyed by email because the account
 *  store only exposes email + role; nothing here is sent to the server. */

const STORAGE_KEY = "bv-profile-prefs";
export const PREFS_CHANGED_EVENT = "bv-profile-prefs-changed";

export const AVATAR_SWATCHES = [
  { id: "accent", bg: "var(--accent-subtle)", color: "var(--accent)" },
  { id: "gold", bg: "var(--gold-subtle)", color: "var(--gold)" },
  { id: "success", bg: "var(--success-subtle)", color: "var(--success)" },
  { id: "navy", bg: "var(--surface-sunken)", color: "var(--brand-navy)" },
];

function readAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function writeAll(all) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // Private browsing — prefs degrade silently.
  }
}

/** Turn `nguyen.van` into a readable default display name. */
export function defaultDisplayName(email) {
  if (!email) return "";
  const local = email.split("@")[0] || "";
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function defaultProfilePrefs(email) {
  return {
    displayName: defaultDisplayName(email),
    avatarSwatch: "accent",
  };
}

export function loadProfilePrefs(email) {
  if (!email) return defaultProfilePrefs("");
  const stored = readAll()[email];
  if (!stored || typeof stored !== "object") return defaultProfilePrefs(email);
  return {
    ...defaultProfilePrefs(email),
    ...stored,
    displayName: stored.displayName?.trim() || defaultDisplayName(email),
    avatarSwatch: AVATAR_SWATCHES.some((s) => s.id === stored.avatarSwatch)
      ? stored.avatarSwatch
      : "accent",
  };
}

export function saveProfilePrefs(email, prefs) {
  if (!email) return null;
  const all = readAll();
  const next = { ...loadProfilePrefs(email), ...prefs };
  all[email] = next;
  writeAll(all);
  window.dispatchEvent(new CustomEvent(PREFS_CHANGED_EVENT, { detail: { email, prefs: next } }));
  return next;
}

/** Merge server-side prefs from GET /me into local cache (server wins when set). */
export function applyServerProfilePrefs(email, me) {
  if (!email) return defaultProfilePrefs("");
  const local = loadProfilePrefs(email);
  const merged = {
    ...local,
    displayName: me?.display_name?.trim() || local.displayName,
    avatarSwatch:
      me?.avatar_swatch && AVATAR_SWATCHES.some((s) => s.id === me.avatar_swatch)
        ? me.avatar_swatch
        : local.avatarSwatch,
  };
  const all = readAll();
  all[email] = merged;
  writeAll(all);
  window.dispatchEvent(new CustomEvent(PREFS_CHANGED_EVENT, { detail: { email, prefs: merged } }));
  return merged;
}

export async function syncProfilePrefsToServer(prefs) {
  const body = {};
  if (prefs.displayName != null) body.display_name = prefs.displayName;
  if (prefs.avatarSwatch != null) body.avatar_swatch = prefs.avatarSwatch;
  const resp = await fetch("/me", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export function avatarStyle(swatchId) {
  return AVATAR_SWATCHES.find((s) => s.id === swatchId) ?? AVATAR_SWATCHES[0];
}

export function roleLabel(role) {
  if (role === "admin") return "Quản trị viên";
  if (role === "employee") return "Nhân viên";
  return "";
}
