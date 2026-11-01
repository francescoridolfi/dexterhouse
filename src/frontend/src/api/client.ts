// SPDX-License-Identifier: AGPL-3.0-or-later

/** Error raised for non-2xx responses from the core. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * GET a same-origin JSON resource. Paths are absolute (`/api/v1/...`, `/health/...`):
 * the Vite dev server and nginx both proxy them to the Django core.
 */
export async function getJson(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(path, {
    ...init,
    method: "GET",
    headers: { Accept: "application/json", ...init?.headers },
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed with HTTP ${response.status}`);
  }
  return response.json();
}
