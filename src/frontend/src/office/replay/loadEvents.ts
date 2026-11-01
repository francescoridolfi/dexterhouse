// SPDX-License-Identifier: AGPL-3.0-or-later
// Pages of GET /projects/{id}/events?to&types (oldest first) until the cursor ends.
import { api } from "../../api/endpoints.ts";
import type { EventEnvelope } from "../../api/types.ts";

/** What the replay applies (the store and the office reducers); speech is not persisted. */
export const REPLAY_TYPES = [
  "project.created",
  "project.started",
  "project.waiting",
  "project.resumed",
  "project.paused",
  "project.completed",
  "project.failed",
  "project.retried",
  "project.archived",
  "project.budget_changed",
  "process.started",
  "process.completed",
  "process.failed",
  "phase.ready",
  "phase.started",
  "phase.step.completed",
  "phase.reopened",
  "phase.completed",
  "phase.failed",
  "phase.skipped",
  "agent.hired",
  "agent.released",
  "agent.moved",
  "agent.status",
  "agent.turn.started",
  "agent.turn.completed",
  "agent.turn.failed",
  "agent.turn.cancelled",
  "agent.tool.used",
  "task.created",
  "task.updated",
  "task.ready",
  "task.started",
  "task.step.completed",
  "task.iteration",
  "task.completed",
  "task.escalated",
  "task.cancelled",
  "gate.opened",
  "gate.decided",
  "gate.expired",
  "question.answered",
  "workspace.created",
  "workspace.idle",
  "workspace.resumed",
  "workspace.destroyed",
  "test.run.started",
  "test.run.completed",
  "release.prepared",
  "release.delivered",
  "release.failed",
  "package.installing",
  "package.installed",
  "package.rejected",
  "budget.warning",
  "budget.exceeded",
  "security.violation",
  "security.turn_blocked",
];

export async function loadEvents(
  projectId: string,
  to: string,
  onProgress: (loaded: number) => void,
  signal: AbortSignal,
): Promise<EventEnvelope[]> {
  const events: EventEnvelope[] = [];
  let page = await api.events(projectId, { to, types: REPLAY_TYPES.join(",") });
  for (;;) {
    if (signal.aborted) throw new DOMException("aborted", "AbortError");
    events.push(...page.results);
    onProgress(events.length);
    if (!page.next) return events;
    page = await api.events(projectId, {}, page.next);
  }
}
