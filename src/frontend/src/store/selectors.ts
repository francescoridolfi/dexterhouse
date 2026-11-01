// SPDX-License-Identifier: AGPL-3.0-or-later
// Derived views of the project state. Pure: usable by the 2D views, the 3D office and tests.
import type { TaskStatus } from "../api/types.ts";
import type { AgentView, GateView, PhaseView, ProjectState, TaskView } from "./model.ts";

export const BOARD_COLUMNS: { id: string; statuses: TaskStatus[] }[] = [
  { id: "backlog", statuses: ["pending"] },
  { id: "ready", statuses: ["ready"] },
  { id: "in_progress", statuses: ["in_progress"] },
  { id: "in_review", statuses: ["in_review"] },
  { id: "in_test", statuses: ["in_test"] },
  { id: "done", statuses: ["done"] },
  { id: "escalated", statuses: ["escalated"] },
];

export function orderedPhases(state: ProjectState): PhaseView[] {
  return state.phaseOrder.map((id) => state.phases[id]).filter((p): p is PhaseView => !!p);
}

export function openGates(state: ProjectState): GateView[] {
  return Object.values(state.gates)
    .filter((g) => g.status === "open")
    .sort((a, b) => a.openedAt.localeCompare(b.openedAt));
}

/** Escalations first, then the oldest gate: what the banner shows. */
export function primaryGate(state: ProjectState): GateView | null {
  const open = openGates(state);
  return open.find((g) => g.type === "escalation") ?? open[0] ?? null;
}

export function boardColumns(state: Pick<ProjectState, "tasks">): Record<string, TaskView[]> {
  const columns: Record<string, TaskView[]> = {};
  for (const column of BOARD_COLUMNS) columns[column.id] = [];
  for (const task of Object.values(state.tasks)) {
    if (task.kind === "fix" && task.parent) continue; // fixes show on their parent card
    const column = BOARD_COLUMNS.find((c) => c.statuses.includes(task.status));
    if (column) columns[column.id]?.push(task);
  }
  for (const list of Object.values(columns)) list.sort((a, b) => a.order - b.order);
  return columns;
}

export function teamList(state: ProjectState): AgentView[] {
  return Object.values(state.agents)
    .filter((a) => a.status !== "released")
    .sort((a, b) => {
      const rank = (x: AgentView) => (x.status === "working" ? 0 : x.status === "blocked" ? 1 : 2);
      return rank(a) - rank(b) || a.role.localeCompare(b.role);
    });
}

export interface PhaseProgress {
  done: number;
  total: number;
}

/** Tasks done / total for a loop phase (e.g. "implementation (7/9)"). */
export function phaseProgress(state: ProjectState, phase: PhaseView): PhaseProgress | null {
  const tasks = Object.values(state.tasks).filter(
    (t) =>
      !t.parent &&
      t.status !== "cancelled" &&
      (!phase.runId || t.phase_run === phase.runId || !t.phase_run),
  );
  if (tasks.length === 0 || phase.phaseId !== currentLoopPhase(state)) return null;
  return { done: tasks.filter((t) => t.status === "done").length, total: tasks.length };
}

function currentLoopPhase(state: ProjectState): string | null {
  const withTasks = new Set(Object.values(state.tasks).map((t) => t.phase_run));
  return orderedPhases(state).find((p) => p.runId && withTasks.has(p.runId))?.phaseId ?? null;
}

export type BudgetLevel = "ok" | "warn" | "over";

export function budgetLevel(spent: number, budget: number): BudgetLevel {
  if (budget <= 0) return spent > 0 ? "over" : "ok";
  const pct = spent / budget;
  return pct >= 1 ? "over" : pct >= 0.8 ? "warn" : "ok";
}

/** One-line accessible description of the office, for `role="img"` (ux_2d_states.md). */
export function officeDescription(state: ProjectState): string {
  const team = teamList(state);
  const working = team.filter((a) => a.status === "working");
  const parts = [`${team.length} agents`];
  for (const agent of working) parts.push(`${agent.displayName} working in ${agent.room}`);
  return parts.join(", ");
}
