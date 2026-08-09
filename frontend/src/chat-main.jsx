import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./tokens/styles.css";
import { LocaleProvider } from "./i18n/LocaleContext.jsx";
import { ChatScreen } from "./chat/ChatScreen.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <LocaleProvider>
      <ChatScreen />
    </LocaleProvider>
  </StrictMode>,
);
