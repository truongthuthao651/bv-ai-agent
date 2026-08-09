import { ThemeToggle } from "../components/index.js";
import { useTheme } from "../theme/useTheme.js";

/** Each panel is a real iframe document, not a nested data-theme div: the
 *  vendored tokens/colors.css defines `:root` (light) and `[data-theme="dark"]`
 *  (override) but no `[data-theme="light"]` reset, so a nested light div
 *  inside a dark page just inherits the ancestor's dark values — `:root` only
 *  ever matches an actual document root. An iframe's document has its own
 *  root, so ?theme=light / ?theme=dark force each panel correctly without
 *  duplicating token values into a local override that could drift from the
 *  design system. */
function ThemeFrame({ theme, title }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
      }}
    >
      <div
        style={{
          fontSize: "var(--text-2xs)",
          fontWeight: "var(--weight-bold)",
          textTransform: "uppercase",
          letterSpacing: "var(--tracking-wide)",
          color: "var(--text-muted)",
        }}
      >
        {title}
      </div>
      <iframe
        title={title}
        src={`?embed=1&theme=${theme}`}
        style={{
          width: "100%",
          height: 2200,
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-xl)",
        }}
      />
    </div>
  );
}

export function Showcase() {
  const { theme, setTheme } = useTheme();

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", fontFamily: "var(--font-sans)" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-4)",
          padding: "var(--space-4) var(--pad-page)",
          borderBottom: "1px solid var(--border)",
          background: "var(--surface)",
        }}
      >
        <h1
          style={{
            margin: 0,
            fontSize: "var(--text-lg)",
            fontWeight: "var(--weight-semibold)",
            color: "var(--text-primary)",
          }}
        >
          BV AI Agent — Phase 0 component showcase
        </h1>
        <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
          Throwaway page — not shipped. Live toggle drives this page's own theme; the two frames below embed the
          same build forced to each theme, for side-by-side comparison.
        </p>
        <div style={{ marginLeft: "auto" }}>
          <ThemeToggle theme={theme} onChange={setTheme} />
        </div>
      </header>

      <main style={{ display: "flex", gap: "var(--gap-section)", padding: "var(--pad-page)", alignItems: "flex-start" }}>
        <ThemeFrame theme="light" title="Forced light" />
        <ThemeFrame theme="dark" title="Forced dark" />
      </main>
    </div>
  );
}
