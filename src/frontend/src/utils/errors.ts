// SPDX-License-Identifier: AGPL-3.0-or-later
import { ApiError } from "../api/client.ts";

export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}
