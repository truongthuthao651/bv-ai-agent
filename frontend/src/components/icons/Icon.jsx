import React from "react";

/** Lightweight inline SVG icons — stroke style, 24×24 viewBox. No external library. */
const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

const paths = {
  menu: (
    <>
      <line x1="4" y1="7" x2="20" y2="7" {...STROKE} />
      <line x1="4" y1="12" x2="20" y2="12" {...STROKE} />
      <line x1="4" y1="17" x2="20" y2="17" {...STROKE} />
    </>
  ),
  close: (
    <>
      <line x1="6" y1="6" x2="18" y2="18" {...STROKE} />
      <line x1="18" y1="6" x2="6" y2="18" {...STROKE} />
    </>
  ),
  edit: (
    <>
      <path d="M12 20h9" {...STROKE} />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" {...STROKE} />
    </>
  ),
  trash: (
    <>
      <path d="M3 6h18" {...STROKE} />
      <path d="M8 6V4h8v2" {...STROKE} />
      <path d="M6 6l1 14h10l1-14" {...STROKE} />
      <line x1="10" y1="11" x2="10" y2="17" {...STROKE} />
      <line x1="14" y1="11" x2="14" y2="17" {...STROKE} />
    </>
  ),
  logout: (
    <>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" {...STROKE} />
      <polyline points="16 17 21 12 16 7" {...STROKE} />
      <line x1="21" y1="12" x2="9" y2="12" {...STROKE} />
    </>
  ),
  moon: <path d="M21 14.5A8.5 8.5 0 1 1 9.5 3 7 7 0 0 0 21 14.5Z" {...STROKE} />,
  sun: (
    <>
      <circle cx="12" cy="12" r="4" {...STROKE} />
      <line x1="12" y1="2" x2="12" y2="4" {...STROKE} />
      <line x1="12" y1="20" x2="12" y2="22" {...STROKE} />
      <line x1="4.2" y1="4.2" x2="5.6" y2="5.6" {...STROKE} />
      <line x1="18.4" y1="18.4" x2="19.8" y2="19.8" {...STROKE} />
      <line x1="2" y1="12" x2="4" y2="12" {...STROKE} />
      <line x1="20" y1="12" x2="22" y2="12" {...STROKE} />
      <line x1="4.2" y1="19.8" x2="5.6" y2="18.4" {...STROKE} />
      <line x1="18.4" y1="5.6" x2="19.8" y2="4.2" {...STROKE} />
    </>
  ),
  "chevron-left": <polyline points="15 6 9 12 15 18" {...STROKE} />,
  "chevron-down": <polyline points="6 9 12 15 18 9" {...STROKE} />,
  "arrow-up": (
    <>
      <line x1="12" y1="19" x2="12" y2="5" {...STROKE} />
      <polyline points="5 12 12 5 19 12" {...STROKE} />
    </>
  ),
  "arrow-left": (
    <>
      <line x1="19" y1="12" x2="5" y2="12" {...STROKE} />
      <polyline points="12 19 5 12 12 5" {...STROKE} />
    </>
  ),
  "arrow-right": (
    <>
      <line x1="5" y1="12" x2="19" y2="12" {...STROKE} />
      <polyline points="12 5 19 12 12 19" {...STROKE} />
    </>
  ),
  "external-link": (
    <>
      <path d="M15 3h6v6" {...STROKE} />
      <path d="M10 14 21 3" {...STROKE} />
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" {...STROKE} />
    </>
  ),
  plus: (
    <>
      <line x1="12" y1="5" x2="12" y2="19" {...STROKE} />
      <line x1="5" y1="12" x2="19" y2="12" {...STROKE} />
    </>
  ),
  "thumbs-down": (
    <>
      <path d="M10 15v6" {...STROKE} />
      <path d="M14 9v12" {...STROKE} />
      <path d="M10 21H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h2l3-6a2 2 0 0 1 2-2h1a2 2 0 0 1 2 2v4h4a2 2 0 0 1 2 2l-1 7a2 2 0 0 1-2 2h-6Z" {...STROKE} />
    </>
  ),
  "alert-triangle": (
    <>
      <path d="M12 3 22 21H2Z" {...STROKE} />
      <line x1="12" y1="9" x2="12" y2="13" {...STROKE} />
      <line x1="12" y1="17" x2="12.01" y2="17" {...STROKE} />
    </>
  ),
  square: <rect x="6" y="6" width="12" height="12" rx="1" {...STROKE} />,
  "trend-up": (
    <>
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" {...STROKE} />
      <polyline points="17 6 23 6 23 12" {...STROKE} />
    </>
  ),
  "trend-down": (
    <>
      <polyline points="23 18 13.5 8.5 8.5 13.5 1 6" {...STROKE} />
      <polyline points="17 18 23 18 23 12" {...STROKE} />
    </>
  ),
};

export function Icon({ name, size = 16, color = "currentColor", style, title, ...rest }) {
  const content = paths[name];
  if (!content) return null;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      style={{ display: "block", flexShrink: 0, color, ...style }}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {content}
    </svg>
  );
}
