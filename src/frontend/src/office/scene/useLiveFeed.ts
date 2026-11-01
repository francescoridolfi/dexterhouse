// SPDX-License-Identifier: AGPL-3.0-or-later
// Live mode: the office follows the project store. History already in the store seeds the
// office without animation; every new event then goes through the pure office reducer.
import { useEffect } from "react";

import type { EventEnvelope } from "../../api/types.ts";
import { useProjectStore } from "../../store/projectStore.ts";
import type { ProjectState } from "../../store/model.ts";
import { emptyOffice } from "../state/model.ts";
import { reconcile, reduceOffice, settle } from "../state/reducer.ts";
import type { OfficeRuntimeStore } from "./runtime.ts";

/** Events after `lastId` (the store keeps them sorted; older history is merged before). */
export function newEvents(events: EventEnvelope[], lastId: string | null): EventEnvelope[] {
  if (!lastId) return events;
  for (let i = events.length - 1; i >= 0; i--)
    if (events[i]!.id === lastId) return events.slice(i + 1);
  return [];
}

export function seedOffice(state: ProjectState) {
  let model = reconcile(emptyOffice(), state, 0);
  for (const event of state.events) model = reduceOffice(model, event, state, 0);
  return settle(reconcile(model, state, 0));
}

export function useLiveFeed(runtime: OfficeRuntimeStore, enabled: boolean, clock: () => number) {
  useEffect(() => {
    if (!enabled) return;
    const start = useProjectStore.getState();
    runtime.getState().replace(seedOffice(start));
    let lastId = start.events.at(-1)?.id ?? null;
    return useProjectStore.subscribe((state, prev) => {
      const office = runtime.getState();
      if (state.events !== prev.events) {
        const fresh = newEvents(state.events, lastId);
        if (fresh.length > 0) lastId = fresh.at(-1)!.id;
        else if (!state.events.some((e) => e.id === lastId))
          lastId = state.events.at(-1)?.id ?? null;
        for (const event of fresh) office.apply(event, state, clock());
      }
      if (state.agents !== prev.agents) office.reconcile(state, clock());
    });
  }, [runtime, enabled, clock]);
}
