import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./tokens/styles.css";
import { LocaleProvider } from "./i18n/LocaleContext.jsx";
import { LandingScreen } from "./landing/LandingScreen.jsx";

// Public entry point ("/"). There is exactly one real gate today (the shared
// admin password) — see LandingScreen.jsx's header comment — so the only
// destination is /login.
function handleEnter() {
  window.location.href = "/login";
}

function LandingApp() {
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  }, []);

  return (
    <LocaleProvider>
      <LandingScreen onEnter={handleEnter} />
    </LocaleProvider>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <LandingApp />
  </StrictMode>,
);
