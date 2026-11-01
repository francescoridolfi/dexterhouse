// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it, vi } from "vitest";

import { event, gate, snapshot, task } from "../test/fixtures.ts";
import { emptyState } from "./model.ts";
import { applyEvent, applySnapshot, applySpeaking, mergeHistory } from "./reducer.ts";
import {
  boardColumns,
  budgetLevel,
  officeDescription,
  openGates,
  primaryGate,
  teamList,
} from "./selectors.ts";

const start = () => applySnapshot(emptyState(), snapshot());
const apply = (state: ReturnType<typeof start>, ...events: Parameters<typeof applyEvent>[1][]) =>
  events.reduce(applyEvent, state);

describe("applySnapshot", () => {
  it("normalises phases, agents, rooms and budget", () => {
    const state = start();
    expect(state.phaseOrder).toEqual(["analysis", "implementation"]);
    expect(state.phases.analysis?.runId).toBe("run-analysis");
    expect(state.agents["a-2"]?.color).toBe("#123456");
    expect(state.rooms).toEqual({ meeting_room: ["a-1"], break_room: ["a-2"] });
    expect(state.budget).toMatchObject({ budget: 20, spent: 1, warning: false, exceeded: false });
    expect(state.snapshotLoaded).toBe(true);
  });

  it("maps open gates to their phase and keeps the history of the same project", () => {
    const first = apply(start(), event("note.added", { note_id: "n", excerpt: "hi" }));
    const again = applySnapshot(first, snapshot({ gates_open: [gate()] }));
    expect(again.gates["g-1"]?.phaseId).toBe("analysis");
    expect(again.events).toHaveLength(1);
  });
});

describe("applyEvent", () => {
  it("moves agents between rooms and tracks turns", () => {
    const state = apply(
      start(),
      event("agent.turn.started", {
        turn_id: "turn-1",
        agent_id: "a-2",
        room: "open_space",
        purpose: "T-01",
      }),
      event("agent.moved", { agent_id: "a-1", from_room: "meeting_room", to_room: "break_room" }),
    );
    expect(state.agents["a-2"]).toMatchObject({
      status: "working",
      room: "open_space",
      turnId: "turn-1",
    });
    expect(state.rooms.break_room).toEqual(["a-1"]);
    const done = apply(
      state,
      event("agent.turn.completed", {
        turn_id: "turn-1",
        agent_id: "a-2",
        cost: "0.5",
        artifacts: [{ id: "art", kind: "dev_notes", version: 1 }],
      }),
    );
    expect(done.agents["a-2"]?.turnId).toBeNull();
    expect(done.artifacts.art?.kind).toBe("dev_notes");
    expect(done.budget.spent).toBeCloseTo(1.5);
  });

  it("follows a phase and its gate through the pipeline", () => {
    let state = apply(
      start(),
      event("gate.opened", {
        gate_id: "g-9",
        type: "approval",
        phase_id: "analysis",
        title: "Approve",
        summary: "s",
        artifacts: [],
      }),
    );
    expect(state.phases.analysis?.status).toBe("waiting_gate");
    expect(primaryGate(state)?.id).toBe("g-9");
    state = apply(
      state,
      event("gate.decided", {
        gate_id: "g-9",
        type: "approval",
        decision: "approve",
        decided_by: { id: "u", name: "ada" },
        auto: false,
        next: "phase_completed",
      }),
      event("phase.completed", { phase_id: "analysis", duration_s: 60, cost: "0.42" }),
      event("phase.started", {
        phase_id: "implementation",
        room: "open_space",
        agents: ["a-2"],
        workspace_required: true,
      }),
    );
    expect(openGates(state)).toHaveLength(0);
    expect(state.gates["g-9"]).toMatchObject({ status: "decided", decidedBy: "ada" });
    expect(state.phases.analysis).toMatchObject({
      status: "completed",
      cost: "0.42",
      durationS: 60,
    });
    expect(state.phases.implementation?.status).toBe("running");
  });

  it("builds the board from task events", () => {
    const state = apply(
      applySnapshot(emptyState(), snapshot({ tasks: [task()] })),
      event("task.created", {
        task_id: "t-2",
        external_id: "T-02",
        kind: "feature",
        iteration: 1,
        title: "Waitlist",
        assigned_role: "developer",
        depends_on: ["t-1"],
        estimate: "S",
      }),
      event("task.started", { task_id: "t-1", agent_id: "a-2", branch: "t-01", iteration: 1 }),
      event("task.step.completed", {
        task_id: "t-1",
        step: "developer",
        agent_id: "a-2",
        artifact: {},
      }),
      event("task.iteration", {
        task_id: "t-1",
        iteration: 2,
        max_iterations: 3,
        reason: "review",
        fix_task_id: "x",
      }),
      event("task.completed", {
        task_id: "t-2",
        iterations: 1,
        duration_s: 1,
        cost: "1.10",
        merged_commit: "abc",
        forced: false,
      }),
    );
    const columns = boardColumns(state);
    expect(columns.in_progress?.map((t) => t.external_id)).toEqual(["T-01"]);
    expect(columns.done?.[0]).toMatchObject({ external_id: "T-02", cost: "1.10" });
    expect(state.tasks["t-1"]).toMatchObject({ iteration: 2, branch: "t-01" });
  });

  it("tracks project status, budget thresholds and resume with an open gate", () => {
    let state = apply(
      start(),
      event("budget.warning", { spent: "16", budget: "20", pct: 80 }),
      event("budget.exceeded", { spent: "21", budget: "20", gate_id: "g-b" }),
      event("project.waiting", { reason: "budget", gate_id: "g-b" }),
    );
    expect(state.budget).toMatchObject({ exceeded: true, warning: false, spent: 21 });
    expect(state.project).toMatchObject({ status: "waiting", waiting_reason: "budget" });
    state = apply(state, event("project.budget_changed", { old: "20", new: "30" }));
    expect(state.budget).toMatchObject({ budget: 30, exceeded: false });
    state = apply(
      state,
      event("gate.opened", {
        gate_id: "g-2",
        type: "question",
        phase_id: "analysis",
        title: "Q",
        summary: "",
        artifacts: [],
      }),
      event("project.resumed", { reason: "budget" }),
    );
    expect(state.project).toMatchObject({ status: "waiting", waiting_reason: "gate" });
    state = apply(
      state,
      event("project.paused"),
      event("project.completed", { duration_s: 1, cost: "2", tasks_done: 1, iterations_total: 1 }),
    );
    expect(state.project?.status).toBe("completed");
  });

  it("ignores unknown types, other projects and duplicates", () => {
    const debug = vi.spyOn(console, "debug").mockImplementation(() => undefined);
    const known = event("note.added", { excerpt: "x" });
    const state = apply(
      start(),
      event("future.thing", {}),
      event("note.added", {}, { project_id: "other" }),
      known,
      known,
    );
    expect(state.unknownEvents).toBe(1);
    expect(state.events.map((e) => e.id)).toEqual([known.id]);
    expect(debug).toHaveBeenCalled();
  });

  it("handles hires, releases, status and process events", () => {
    const state = apply(
      start(),
      event("process.started", {
        phases: [{ id: "release", needs: ["implementation"], room: "release_dock" }],
      }),
      event("agent.hired", {
        agent_id: "a-9",
        role: "htmx_dev",
        display_name: "HTMX Dev",
        room: "hr_office",
        avatar: { color: "#E79D7D" },
        package: {},
        source: "marketplace",
        allowed_tools: [],
      }),
      event("agent.status", { agent_id: "a-9", status: "blocked" }),
      event("agent.released", { agent_id: "a-1", reason: "done" }),
      event("phase.reopened", { phase_id: "analysis", round: 1, comment: "c" }),
      event("phase.ready", { phase_id: "release" }),
      event("phase.skipped", { phase_id: "release" }),
    );
    expect(state.phaseOrder).toContain("release");
    expect(state.phases.release?.status).toBe("skipped");
    expect(state.phases.analysis).toMatchObject({ status: "reopened", round: 1 });
    expect(teamList(state).map((a) => a.id)).toEqual(["a-9", "a-2"]);
    expect(officeDescription(state)).toContain("2 agents");
  });
});

describe("speaking and history", () => {
  it("replaces the stream text and drops older chunks", () => {
    let state = applySpeaking(start(), { agentId: "a-1", turnId: "t", text: "Hel", seq: 1 });
    state = applySpeaking(state, { agentId: "a-1", turnId: "t", text: "Hello", seq: 2 });
    state = applySpeaking(state, { agentId: "a-1", turnId: "t", text: "stale", seq: 1 });
    expect(state.speaking["a-1"]?.text).toBe("Hello");
    const done = apply(
      state,
      event("agent.turn.completed", { turn_id: "t", agent_id: "a-1", cost: "0" }),
    );
    expect(done.speaking["a-1"]).toBeUndefined();
  });

  it("merges older REST events in order without touching the state", () => {
    const live = event("note.added", { excerpt: "new" });
    const older = event("project.created", {}, { created_at: "2026-11-01T09:00:00Z" });
    const state = mergeHistory(apply(start(), live), [older, live]);
    expect(state.events.map((e) => e.id)).toEqual([older.id, live.id]);
    expect(mergeHistory(state, [])).toBe(state);
  });
});

describe("budgetLevel", () => {
  it("is ok below 80 %, warn up to 100 %, over beyond", () => {
    expect(budgetLevel(10, 20)).toBe("ok");
    expect(budgetLevel(16, 20)).toBe("warn");
    expect(budgetLevel(20, 20)).toBe("over");
    expect(budgetLevel(1, 0)).toBe("over");
    expect(budgetLevel(0, 0)).toBe("ok");
  });
});
