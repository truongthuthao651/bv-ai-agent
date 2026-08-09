import React from "react";
import { Icon } from "./Icon.jsx";

const baseStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  border: "none",
  background: "transparent",
  color: "var(--text-muted)",
  cursor: "pointer",
  borderRadius: "var(--radius-sm)",
  padding: 0,
  flexShrink: 0,
  transition: "background 150ms, color 150ms",
};

/** Icon-only control with consistent size, hover, and keyboard focus. */
export function IconButton({
  icon,
  label,
  onClick,
  size = 28,
  iconSize = 16,
  color,
  hoverColor,
  danger = false,
  style,
  disabled,
  type = "button",
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const tone = danger && hover ? "var(--danger)" : hover ? hoverColor || "var(--text-primary)" : color || "var(--text-muted)";

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className="bv-focus-ring"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      {...rest}
      style={{
        ...baseStyle,
        width: size,
        height: size,
        color: tone,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.45 : 1,
        ...(hover && !disabled ? { background: "var(--hover)" } : null),
        ...style,
      }}
    >
      <Icon name={icon} size={iconSize} />
    </button>
  );
}
