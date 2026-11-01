// SPDX-License-Identifier: AGPL-3.0-or-later
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Django core (ASGI). Override with DH_CORE_URL, e.g. http://web:8000 inside compose.
const coreUrl = process.env.DH_CORE_URL ?? "http://localhost:8000";

const proxied = { target: coreUrl, changeOrigin: false };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api/": proxied,
      "/ws/": { ...proxied, ws: true },
      "/health/": proxied,
      "/admin": proxied,
      "/static/": proxied,
    },
  },
  preview: {
    port: 4173,
    strictPort: true,
  },
  build: {
    sourcemap: true,
    // The lazy 3D chunk (three + R3F, ~250 kB gzip) is loaded only by the Office tab.
    chunkSizeWarningLimit: 1_000,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
