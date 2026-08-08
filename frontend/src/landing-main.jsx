import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./tokens/styles.css";
import { LandingScreen } from "./landing/LandingScreen.jsx";

// Public entry point ("/"). There is exactly one real gate today (the shared
// admin password) — see LandingScreen.jsx's header comment — so the only
// destination is /login.
function handleEnter() {
  window.location.href = "/login";
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <LandingScreen onEnter={handleEnter} />
  </StrictMode>,
);
