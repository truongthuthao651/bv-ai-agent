import { useEffect } from "react";
import { ComponentGallery } from "./ComponentGallery.jsx";

/** Rendered in its own iframe document (?theme=light|dark) so `:root` in the
 *  vendored tokens/colors.css — which only matches an actual document root,
 *  not a nested data-theme div — resolves correctly for the forced theme.
 *  Nesting a `data-theme="light"` div inside a page whose <html> is
 *  data-theme="dark" does NOT work: the design system defines `:root`
 *  (light) and `[data-theme="dark"]` (override) but no `[data-theme="light"]`
 *  reset, so a nested light div just inherits the ancestor's dark values.
 *  A real document root sidesteps that instead of duplicating token values
 *  into a local override that could drift from the source of truth. */
export function ForcedThemeView({ theme }) {
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", padding: "var(--pad-page)" }}>
      <ComponentGallery />
    </div>
  );
}
