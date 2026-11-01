// SPDX-License-Identifier: AGPL-3.0-or-later
// Typed REST client for the core (`/api/v1`). The 3D office never imports from here.
export { ApiError, csrfToken, getJson, request, setOrganization } from "./client.ts";
export { api, type DecideBody, type NewProject, type ProjectFilters } from "./endpoints.ts";
export * from "./types.ts";
