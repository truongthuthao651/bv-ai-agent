import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./tokens/styles.css";
import { LocaleProvider } from "./i18n/LocaleContext.jsx";
import { AdminShell } from "./admin/AdminShell.jsx";

const params = new URLSearchParams(window.location.search);
const showcase = params.get("showcase") === "1";

// The component showcase (Phase 0) stays reachable at ?showcase=1 for visual
// reference while later phases build against it — production entry is the
// admin console.
async function render() {
  let root;
  if (showcase) {
    const { Showcase } = await import("./showcase/Showcase.jsx");
    const { ForcedThemeView } = await import("./showcase/ForcedThemeView.jsx");
    const embedded = params.get("embed") === "1";
    const forcedTheme = params.get("theme");
    root =
      embedded && (forcedTheme === "light" || forcedTheme === "dark") ? (
        <ForcedThemeView theme={forcedTheme} />
      ) : (
        <Showcase />
      );
  } else {
    root = (
      <LocaleProvider>
        <AdminShell />
      </LocaleProvider>
    );
  }
  createRoot(document.getElementById("root")).render(<StrictMode>{root}</StrictMode>);
}

render();
