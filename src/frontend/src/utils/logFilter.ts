// SPDX-License-Identifier: AGPL-3.0-or-later
import type { EventEnvelope } from "../api/types.ts";

export interface LogFilters {
  family: string;
  agent: string;
  phase: string;
  text: string;
}

/** Client-side filter over the loaded history (type, agent, phase, text). */
export function filterEvents(
  events: EventEnvelope[],
  filters: LogFilters,
  describe: (event: EventEnvelope) => string,
): EventEnvelope[] {
  const text = filters.text.trim().toLowerCase();
  return events.filter((event) => {
    if (filters.family && !event.type.startsWith(`${filters.family}.`)) return false;
    if (
      filters.agent &&
      event.payload.agent_id !== filters.agent &&
      event.actor.id !== filters.agent
    )
      return false;
    if (filters.phase && event.payload.phase_id !== filters.phase) return false;
    if (
      text &&
      !`${event.type} ${describe(event)} ${JSON.stringify(event.payload)}`
        .toLowerCase()
        .includes(text)
    )
      return false;
    return true;
  });
}
