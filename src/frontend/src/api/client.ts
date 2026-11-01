// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Problem } from "./types.ts";

/** Non-2xx response from the core, with its RFC 9457 problem when there is one. */
export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem | null;

  constructor(status: number, message: string, problem: Problem | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }

  /** `{field: message}` from `problem.errors[]` for inline form errors. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const item of this.problem?.errors ?? []) out[item.field] = item.message;
    return out;
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** The `csrftoken` cookie set by Django; the session cookie itself is HttpOnly. */
export function csrfToken(): string {
  const match = /(?:^|;\s*)csrftoken=([^;]+)/.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : "";
}

let organizationSlug = "";

/** Organization sent as `X-Organization` (multi-organization users). */
export function setOrganization(slug: string): void {
  organizationSlug = slug;
}

async function parseProblem(response: Response): Promise<Problem | null> {
  const type = response.headers.get("Content-Type") ?? "";
  if (!type.includes("json")) return null;
  try {
    return (await response.json()) as Problem;
  } catch {
    return null;
  }
}

/** Same-origin JSON request; nginx and the Vite dev server proxy `/api` to the core. */
export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) headers["X-CSRFToken"] = csrfToken();
  if (organizationSlug) headers["X-Organization"] = organizationSlug;
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const problem = await parseProblem(response);
    const message =
      problem?.detail ?? problem?.title ?? `${method} ${path}: HTTP ${response.status}`;
    throw new ApiError(response.status, message, problem);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const getJson = <T>(path: string) => request<T>("GET", path);
export const postJson = <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {});
export const patchJson = <T>(path: string, body: unknown) => request<T>("PATCH", path, body);
export const putJson = <T>(path: string, body: unknown) => request<T>("PUT", path, body);

export function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
