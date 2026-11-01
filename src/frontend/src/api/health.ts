// SPDX-License-Identifier: AGPL-3.0-or-later
import { getJson } from "./client.ts";

export interface HealthStatus {
  status: string;
}

function isHealthStatus(value: unknown): value is HealthStatus {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    typeof value.status === "string"
  );
}

/** Liveness of the Django core (`GET /health/live`). */
export async function fetchLiveness(signal?: AbortSignal): Promise<HealthStatus> {
  const body = await getJson("/health/live", { signal });
  if (!isHealthStatus(body)) {
    throw new Error("Unexpected /health/live payload");
  }
  return body;
}
