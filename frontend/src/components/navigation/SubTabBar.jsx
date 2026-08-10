/** Secondary tab bar for long admin lists (logs, etc.). */
export function SubTabBar({ tabs, active, onSelect }) {
  return (
    <div
      role="tablist"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "var(--space-1)",
        borderBottom: "1px solid var(--border)",
        marginBottom: "var(--space-5)",
      }}
    >
      {tabs.map((tab) => {
        const selected = tab.key === active;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={selected}
            className="bv-focus-ring"
            onClick={() => onSelect(tab.key)}
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-sm)",
              fontWeight: selected ? "var(--weight-semibold)" : "var(--weight-regular)",
              color: selected ? "var(--accent)" : "var(--text-secondary)",
              padding: "var(--space-3) var(--space-4)",
              marginBottom: -1,
              borderBottom: selected ? "2px solid var(--accent)" : "2px solid transparent",
              transition: "color 150ms, border-color 150ms",
            }}
          >
            {tab.label}
            {tab.count != null && (
              <span style={{ marginLeft: 6, fontSize: "var(--text-2xs)", color: "var(--text-muted)", fontWeight: "var(--weight-regular)" }}>
                ({tab.count})
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
