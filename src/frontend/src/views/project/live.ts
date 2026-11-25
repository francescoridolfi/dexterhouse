// SPDX-License-Identifier: AGPL-3.0-or-later
// REST lists kept fresh by the project WebSocket: when an event of the given families
// arrives, the query is refetched (the store keeps no copy of documents or CRs).
import { type QueryKey, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { e13, e13Keys } from "../../api/e13.ts";
import { useProjectStore } from "../../store/projectStore.ts";

/** Id of the latest event whose type starts with one of `prefixes`. */
export function useLastEventId(prefixes: readonly string[]): string | null {
  return useProjectStore((s) => {
    for (let i = s.events.length - 1; i >= 0; i -= 1) {
      const event = s.events[i];
      if (event && prefixes.some((p) => event.type.startsWith(p))) return event.id;
    }
    return null;
  });
}

export function useInvalidateOn(prefixes: readonly string[], key: QueryKey) {
  const client = useQueryClient();
  const last = useLastEventId(prefixes);
  const seen = useRef(last);
  useEffect(() => {
    if (last === seen.current) return;
    seen.current = last;
    void client.invalidateQueries({ queryKey: key });
    // `key` is rebuilt on every render; its content only changes with the project.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, last]);
}

const CR_EVENTS = ["change_request.", "project.reopened"] as const;

/** CRs of the open project, refreshed by `change_request.*` and `project.reopened`. */
export function useChangeRequests(projectId: string) {
  useInvalidateOn(CR_EVENTS, e13Keys.changeRequests(projectId));
  return useQuery({
    queryKey: e13Keys.changeRequests(projectId),
    queryFn: () => e13.changeRequests(projectId),
    enabled: !!projectId,
    staleTime: 30_000,
  });
}
