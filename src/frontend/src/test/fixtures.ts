// SPDX-License-Identifier: AGPL-3.0-or-later
// Wire-format fixtures shaped like the core's responses.
import type { EventEnvelope, Gate, Project, Snapshot, Task } from "../api/types.ts";

export const PROJECT_ID = "p-1";

export function project(overrides: Partial<Project> = {}): Project {
  return {
    id: PROJECT_ID,
    organization: "default",
    name: "GymBook",
    slug: "gymbook",
    status: "running",
    waiting_reason: null,
    execution_mode: "supervised",
    process: { name: "software-house-default", version: "1.0.0" },
    budget: "20.000000",
    spent: "1.000000",
    spent_unpriced_tokens: 0,
    data_residency: "any",
    delivery_mode: "pull_request",
    remote_repo_url: null,
    remote_token: null,
    gate_overrides: {},
    open_gates_count: 0,
    current_phases: ["analysis"],
    created_by: "ada",
    started_at: "2026-11-01T10:00:00Z",
    completed_at: null,
    created_at: "2026-11-01T09:59:00Z",
    updated_at: "2026-11-01T10:00:00Z",
    ...overrides,
  };
}

export function task(overrides: Partial<Task> = {}): Task {
  return {
    id: "t-1",
    phase_run: "run-impl",
    external_id: "T-01",
    kind: "feature",
    parent: null,
    iteration: 1,
    max_iterations: 3,
    title: "Bookings",
    description: "Book a course",
    acceptance: ["can book"],
    depends_on: [],
    estimate: "M",
    assigned_role: "developer",
    assigned_agent: null,
    status: "pending",
    branch: null,
    order: 0,
    current_step: null,
    result: null,
    created_at: "2026-11-01T10:00:00Z",
    ...overrides,
  };
}

export function gate(overrides: Partial<Gate> = {}): Gate {
  return {
    id: "g-1",
    project: PROJECT_ID,
    phase_run: "run-analysis",
    task: null,
    gate_id: "approve_requirements",
    type: "approval",
    status: "open",
    payload: { title: "Approve analysis", summary: "2 artifacts", artifacts: [] },
    decision: null,
    comment: null,
    answers: null,
    decided_by: null,
    opened_at: "2026-11-01T10:05:00Z",
    decided_at: null,
    expires_at: null,
    ...overrides,
  };
}

export function snapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    type: "snapshot",
    project: project(),
    phases: [
      {
        id: "run-analysis",
        phase_id: "analysis",
        status: "running",
        stage: "steps",
        current_step: 0,
        round: 0,
        reopen_count: 0,
        exit_attempts: 0,
        room: "meeting_room",
        agents: [{ role: "analyst", agent_id: "a-1" }],
        gate: null,
        error_code: null,
        started_at: "2026-11-01T10:00:00Z",
        finished_at: null,
      },
      {
        id: "run-impl",
        phase_id: "implementation",
        status: "pending",
        stage: "steps",
        current_step: 0,
        round: 0,
        reopen_count: 0,
        exit_attempts: 0,
        room: "open_space",
        agents: [],
        gate: null,
        error_code: null,
        started_at: null,
        finished_at: null,
      },
    ],
    tasks: [],
    gates_open: [],
    agents: [
      {
        agent_id: "a-1",
        role: "analyst",
        display_name: "Analyst",
        room: "meeting_room",
        status: "working",
        avatar: {},
      },
      {
        agent_id: "a-2",
        role: "developer",
        display_name: "Developer",
        room: "break_room",
        status: "idle",
        avatar: { color: "#123456" },
      },
    ],
    workspace: null,
    budget: { budget: "20.000000", spent: "1.000000" },
    last_event_id: "e-0",
    ...overrides,
  };
}

let seq = 0;
export function event(
  type: string,
  payload: Record<string, unknown> = {},
  extra: Partial<EventEnvelope> = {},
): EventEnvelope {
  seq += 1;
  return {
    id: `e-${seq}`,
    type,
    schema_version: 1,
    organization_id: "o-1",
    project_id: PROJECT_ID,
    actor: { type: "system", id: null, name: "engine" },
    correlation_id: `c-${seq}`,
    created_at: new Date(Date.UTC(2026, 10, 1, 10, 0, seq)).toISOString(),
    payload,
    ...extra,
  };
}
