/** Golden globe from the Bảo Việt Life logo — single brand-ink badge, cropped asset matte. */
export function BrandGlobe({ size = 24, alt = "" }) {
  const radius = Math.max(4, Math.round(size * 0.22));

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: radius,
        background: "var(--brand-ink)",
        overflow: "hidden",
        boxSizing: "border-box",
      }}
      aria-hidden={alt ? undefined : true}
    >
      <img
        src="/assets/favicon.svg"
        alt={alt}
        draggable={false}
        style={{
          display: "block",
          width: `${Math.round(size * 1.18)}px`,
          height: `${Math.round(size * 1.18)}px`,
          objectFit: "cover",
          flexShrink: 0,
        }}
      />
    </span>
  );
}
