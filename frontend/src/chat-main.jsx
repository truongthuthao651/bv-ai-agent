import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./tokens/styles.css";
import { ChatScreen } from "./chat/ChatScreen.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ChatScreen />
  </StrictMode>,
);
