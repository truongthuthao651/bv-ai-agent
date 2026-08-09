import { Button } from "../buttons/Button.jsx";

const railBtnStyle = {
  border: "none",
  background: "transparent",
  color: "var(--text-muted)",
  cursor: "pointer",
  fontSize: 14,
  padding: 0,
  width: 28,
  height: 28,
  flexShrink: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  borderRadius: "var(--radius-sm)",
};

/** Small header/footer control to hide the rail. */
export function RailCollapseButton({ onClick, label = "Ẩn thanh bên" }) {
  return (
    <button type="button" onClick={onClick} title={label} aria-label={label} style={railBtnStyle}>
      ‹
    </button>
  );
}

/** Shown in the main header when the rail is collapsed (desktop). */
export function RailExpandButton({ onClick, label = "Hiện thanh bên" }) {
  return (
    <Button
      variant="ghost"
      onClick={onClick}
      aria-label={label}
      title={label}
      style={{ ...railBtnStyle, width: 32, height: 32, color: "var(--text-primary)" }}
    >
      ☰
    </Button>
  );
}

/** Desktop sidebar shell: fixed width, drag-to-resize handle, optional collapse. */
export function ResizableRail({ layout, children, collapseLabel = "Ẩn thanh bên" }) {
  if (layout.collapsed) return null;

  return (
    <div style={{ display: "flex", flexShrink: 0, height: "100%" }}>
      <aside
        style={{
          width: layout.width,
          flexShrink: 0,
          borderRight: "1px solid var(--border)",
          background: "var(--surface)",
          display: "flex",
          flexDirection: "column",
          height: "100%",
          boxSizing: "border-box",
          minWidth: 0,
          overflow: "hidden",
        }}
      >
        {children}
      </aside>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={layout.width}
        aria-label="Kéo để thay đổi độ rộng thanh bên"
        onMouseDown={layout.onResizePointerDown}
        className="bv-rail-resize"
        style={{
          width: 6,
          flexShrink: 0,
          cursor: "col-resize",
          position: "relative",
          touchAction: "none",
          background: "transparent",
        }}
      >
        <div className="bv-rail-resize-line" />
        <button
          type="button"
          className="bv-rail-collapse-btn"
          onClick={layout.collapse}
          onMouseDown={(e) => e.stopPropagation()}
          title={collapseLabel}
          aria-label={collapseLabel}
        >
          ‹
        </button>
      </div>
      <style>{`
        .bv-rail-resize-line {
          position: absolute;
          top: 0;
          bottom: 0;
          left: 2px;
          width: 2px;
          background: var(--border);
          opacity: 0;
          transition: opacity 150ms, background 150ms;
          pointer-events: none;
        }
        .bv-rail-collapse-btn {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          width: 18px;
          height: 32px;
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          background: var(--surface);
          color: var(--text-muted);
          cursor: pointer;
          font-size: 11px;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: var(--shadow-sm);
          opacity: 0;
          transition: opacity 150ms;
          padding: 0;
        }
        .bv-rail-resize:hover .bv-rail-resize-line,
        .bv-rail-resize:active .bv-rail-resize-line {
          opacity: 1;
        }
        .bv-rail-resize:active .bv-rail-resize-line {
          background: var(--accent);
        }
        .bv-rail-resize:hover .bv-rail-collapse-btn {
          opacity: 1;
        }
        .bv-rail-collapse-btn:hover {
          color: var(--text-primary);
          border-color: var(--accent);
        }
      `}</style>
    </div>
  );
}
