import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme } from "./hooks/useTheme";
import "./theme/global.css";

// index.html has already set data-theme before first paint; this re-applies it
// from the same module the rest of the app reads, so there is one source of
// truth once React is running.
initTheme();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
