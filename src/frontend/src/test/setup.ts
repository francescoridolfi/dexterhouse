// SPDX-License-Identifier: AGPL-3.0-or-later
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll } from "vitest";

import i18n from "../i18n/index.ts";

beforeAll(async () => {
  await i18n.changeLanguage("en");
});

// Vitest globals are off, so Testing Library cannot register its own cleanup.
afterEach(() => {
  cleanup();
});
