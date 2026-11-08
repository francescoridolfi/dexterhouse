// SPDX-License-Identifier: AGPL-3.0-or-later
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import i18n from "./i18n/index.ts";
import { applyGlassMode } from "./utils/glass.ts";
import { applyTheme } from "./utils/theme.ts";
import "./index.css";

applyTheme();
applyGlassMode();
document.documentElement.lang = i18n.language;

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Root element #root not found");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
