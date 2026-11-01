// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from "react";

import { fetchLiveness } from "../../api/index.ts";

export type CoreHealth =
  { state: "loading" } | { state: "ok"; status: string } | { state: "error"; message: string };

/** Polls-once hook for core liveness; replaced by TanStack Query when server state grows. */
export function useCoreHealth(): CoreHealth {
  const [health, setHealth] = useState<CoreHealth>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchLiveness(controller.signal)
      .then(({ status }) => {
        setHealth({ state: "ok", status });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : "Unknown error";
        setHealth({ state: "error", message });
      });
    return () => {
      controller.abort();
    };
  }, []);

  return health;
}
