import { avatarStyle } from "../../user/profilePrefs.js";

/** Theme-aware avatar circle — shared by chat sidebar, admin rail, and profile. */
export function UserAvatar({ email, swatchId = "accent", size = 32 }) {
  const swatch = avatarStyle(swatchId);
  const letter = email?.[0]?.toUpperCase() ?? "?";

  return (
    <div
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: swatch.bg,
        color: swatch.color,
        border: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: size <= 28 ? "var(--text-2xs)" : "var(--text-xs)",
        fontWeight: "var(--weight-bold)",
        flexShrink: 0,
      }}
    >
      {letter}
    </div>
  );
}
