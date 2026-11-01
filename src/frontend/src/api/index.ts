// SPDX-License-Identifier: AGPL-3.0-or-later
// Typed REST client for the core (`/api/v1`, `/health`). The 3D office never imports from here.
export { ApiError, getJson } from "./client.ts";
export { fetchLiveness, type HealthStatus } from "./health.ts";
