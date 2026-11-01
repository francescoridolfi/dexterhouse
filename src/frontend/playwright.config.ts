// SPDX-License-Identifier: AGPL-3.0-or-later
// E2E smoke against a running stack (`docker compose up`): E2E_BASE_URL, E2E_USER, E2E_PASSWORD.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost",
    locale: "en-GB",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // WebGL 2 without a GPU (CI): the 3D office runs on SwiftShader. E2E_GPU=1 keeps the
        // real GPU (run headed for the frame-time numbers of NFR-P3).
        launchOptions: process.env.E2E_GPU
          ? {}
          : { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] },
      },
    },
  ],
});
