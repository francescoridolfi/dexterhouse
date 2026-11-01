// SPDX-License-Identifier: AGPL-3.0-or-later
// Pure functions: `applySnapshot` and `applyEvent` (contracts/events). Unknown types and
// fields are ignored (forward compatibility); every known event lands in `events`.
import type { EventEnvelope, Gate, Phase, Snapshot, Task, TaskStatus } from "../api/types.ts";
import {
  type AgentView,
  type GateView,
  IDLE_ROOM,
  MAX_EVENTS,
  type PhaseView,
  type ProjectState,
  type Speech,
  emptyState,
} from "./model.ts";

const FAMILIES = [
  "project.",
  "process.",
  "phase.",
  "note.",
  "agent.",
  "task.",
  "gate.",
  "question.",
  "workspace.",
  "branch.",
  "commit.",
  "test.",
  "secrets.",
  "release.",
  "package.",
  "budget.",
  "provider.",
  "security.",
];

type Payload = Record<string, unknown>;

const str = (value: unknown): string | null => (typeof value === "string" ? value : null);
const num = (value: unknown): number | null => {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
    return Number(value);
  }
  return null;
};
const list = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);
const money = (value: unknown): string | null => {
  const n = num(value);
  return n === null ? null : typeof value === "string" ? value : String(n);
};

export function isKnownType(type: string): boolean {
  return FAMILIES.some((prefix) => type.startsWith(prefix));
}

function computeRooms(agents: Record<string, AgentView>): Record<string, string[]> {
  const rooms: Record<string, string[]> = {};
  for (const agent of Object.values(agents)) {
    if (agent.status === "released") continue;
    (rooms[agent.room] ??= []).push(agent.id);
  }
  return rooms;
}

function phaseFromSnapshot(phase: Phase): PhaseView {
  return {
    phaseId: phase.phase_id,
    runId: phase.id,
    status: phase.status,
    room: phase.room,
    needs: [],
    currentStep: phase.current_step,
    round: phase.round,
    startedAt: phase.started_at,
    finishedAt: phase.finished_at,
    durationS:
      phase.started_at && phase.finished_at
        ? (Date.parse(phase.finished_at) - Date.parse(phase.started_at)) / 1000
        : null,
    cost: null,
    agents: phase.agents.map((a) => a.agent_id),
  };
}

export function gateFromRest(gate: Gate, phaseId: string | null = null): GateView {
  return {
    id: gate.id,
    type: gate.type,
    key: gate.gate_id,
    phaseRunId: gate.phase_run,
    phaseId,
    taskId: gate.task,
    title: gate.payload.title,
    summary: gate.payload.summary,
    artifacts: gate.payload.artifacts ?? [],
    questions: gate.payload.questions ?? [],
    reason: gate.payload.reason ?? null,
    status: gate.status,
    openedAt: gate.opened_at,
    decision: gate.decision,
    decidedBy: gate.decided_by?.name ?? null,
    decidedAt: gate.decided_at,
  };
}

function budgetFlags(state: ProjectState, budget: number, spent: number): ProjectState["budget"] {
  const exceeded = budget > 0 ? spent >= budget : spent > 0;
  return {
    ...state.budget,
    budget,
    spent,
    warning: !exceeded && budget > 0 && spent >= budget * 0.8,
    exceeded,
  };
}

export function applySnapshot(state: ProjectState, snapshot: Snapshot): ProjectState {
  const base = emptyState(snapshot.project.id);
  const runToPhase = new Map(snapshot.phases.map((p) => [p.id, p.phase_id]));
  const phases: Record<string, PhaseView> = {};
  for (const phase of snapshot.phases) phases[phase.phase_id] = phaseFromSnapshot(phase);
  const agents: Record<string, AgentView> = {};
  for (const a of snapshot.agents) {
    const color = (a.avatar as { color?: unknown }).color;
    agents[a.agent_id] = {
      id: a.agent_id,
      role: a.role,
      displayName: a.display_name,
      room: a.room,
      status: a.status,
      color: typeof color === "string" ? color : undefined,
      turnId: null,
      purpose: null,
      lastToolAt: null,
    };
  }
  const tasks: ProjectState["tasks"] = {};
  for (const task of snapshot.tasks) {
    tasks[task.id] = { ...task, cost: state.tasks[task.id]?.cost ?? null };
  }
  const gates: Record<string, GateView> = {};
  // Decided gates are history: keep the ones we saw; open ones come from the snapshot.
  for (const gate of Object.values(state.gates)) {
    if (gate.status !== "open" && state.projectId === snapshot.project.id) gates[gate.id] = gate;
  }
  for (const gate of snapshot.gates_open) {
    gates[gate.id] = gateFromRest(gate, runToPhase.get(gate.phase_run) ?? null);
  }
  const same = state.projectId === snapshot.project.id;
  const next: ProjectState = {
    ...base,
    project: snapshot.project,
    mode: snapshot.project.execution_mode,
    phases,
    phaseOrder: snapshot.phases.map((p) => p.phase_id),
    tasks,
    gates,
    agents,
    rooms: computeRooms(agents),
    artifacts: same ? state.artifacts : {},
    events: same ? state.events : [],
    lastEventId: snapshot.last_event_id,
    snapshotLoaded: true,
  };
  next.budget = budgetFlags(next, Number(snapshot.budget.budget), Number(snapshot.budget.spent));
  return next;
}

function patchProject(state: ProjectState, fields: Partial<NonNullable<ProjectState["project"]>>) {
  return state.project ? { ...state, project: { ...state.project, ...fields } } : state;
}

function patchPhase(state: ProjectState, phaseId: string | null, fields: Partial<PhaseView>) {
  if (!phaseId) return state;
  const current: PhaseView = state.phases[phaseId] ?? {
    phaseId,
    runId: null,
    status: "pending",
    room: "",
    needs: [],
    currentStep: 0,
    round: 0,
    startedAt: null,
    finishedAt: null,
    durationS: null,
    cost: null,
    agents: [],
  };
  const order = state.phaseOrder.includes(phaseId)
    ? state.phaseOrder
    : [...state.phaseOrder, phaseId];
  return {
    ...state,
    phases: { ...state.phases, [phaseId]: { ...current, ...fields } },
    phaseOrder: order,
  };
}

function patchTask(
  state: ProjectState,
  taskId: string | null,
  fields: Partial<Task> & { cost?: string | null },
) {
  if (!taskId) return state;
  const current = state.tasks[taskId];
  if (!current) return state;
  return { ...state, tasks: { ...state.tasks, [taskId]: { ...current, ...fields } } };
}

function patchAgent(state: ProjectState, agentId: string | null, fields: Partial<AgentView>) {
  if (!agentId) return state;
  const current = state.agents[agentId];
  if (!current) return state;
  const agents = { ...state.agents, [agentId]: { ...current, ...fields } };
  return { ...state, agents, rooms: computeRooms(agents) };
}

function addArtifacts(
  state: ProjectState,
  refs: unknown,
  event: EventEnvelope,
  phaseId: string | null,
) {
  const items = list<{ id: string; kind: string; version: number }>(refs);
  if (items.length === 0) return state;
  const artifacts = { ...state.artifacts };
  for (const ref of items) {
    artifacts[ref.id] = {
      ...ref,
      phaseId,
      agentId: event.actor.type === "agent" ? event.actor.id : null,
      at: event.created_at,
    };
  }
  return { ...state, artifacts };
}

function hasOpenGate(state: ProjectState): boolean {
  return Object.values(state.gates).some((g) => g.status === "open");
}

function reduceProject(state: ProjectState, type: string, p: Payload): ProjectState {
  switch (type) {
    case "project.started":
      return patchProject(state, { status: "running", waiting_reason: null });
    case "project.waiting":
      return patchProject(state, {
        status: "waiting",
        waiting_reason: (str(p.reason) as "gate" | "budget" | null) ?? "gate",
      });
    case "project.resumed":
      return hasOpenGate(state)
        ? patchProject(state, { status: "waiting", waiting_reason: "gate" })
        : patchProject(state, { status: "running", waiting_reason: null });
    case "project.paused":
      return patchProject(state, { status: "paused" });
    case "project.completed":
      return patchProject(state, { status: "completed" });
    case "project.failed":
      return patchProject(state, { status: "failed" });
    case "project.retried":
      return patchProject(state, { status: "running" });
    case "project.archived":
      return patchProject(state, { status: "archived" });
    case "project.budget_changed": {
      const budget = num(p.new) ?? state.budget.budget;
      const next = patchProject(state, { budget: money(p.new) ?? String(budget) });
      return { ...next, budget: budgetFlags(next, budget, next.budget.spent) };
    }
    default:
      return state;
  }
}

function reducePhase(state: ProjectState, type: string, p: Payload, at: string): ProjectState {
  const phaseId = str(p.phase_id);
  switch (type) {
    case "process.started": {
      let next = state;
      for (const phase of list<{ id: string; needs?: string[]; room?: string }>(p.phases)) {
        next = patchPhase(next, phase.id, {
          needs: phase.needs ?? [],
          room: phase.room ?? next.phases[phase.id]?.room ?? "",
        });
      }
      return next;
    }
    case "phase.ready":
      return patchPhase(state, phaseId, { status: "ready" });
    case "phase.started":
      return patchPhase(state, phaseId, {
        status: "running",
        room: str(p.room) ?? state.phases[phaseId ?? ""]?.room ?? "",
        startedAt: at,
        agents: list<string>(p.agents),
      });
    case "phase.step.completed":
      return patchPhase(state, phaseId, {
        currentStep: (state.phases[phaseId ?? ""]?.currentStep ?? 0) + 1,
      });
    case "phase.reopened":
      return patchPhase(state, phaseId, { status: "reopened", round: num(p.round) ?? 0 });
    case "phase.completed":
      return patchPhase(state, phaseId, {
        status: "completed",
        finishedAt: at,
        durationS: num(p.duration_s),
        cost: money(p.cost),
      });
    case "phase.failed":
      return patchPhase(state, phaseId, { status: "failed", finishedAt: at });
    case "phase.skipped":
      return patchPhase(state, phaseId, { status: "skipped", finishedAt: at });
    default:
      return state;
  }
}

const TASK_STEP_STATUS: Record<string, TaskStatus> = {
  developer: "in_review",
  reviewer: "in_test",
  tester: "in_test",
};

function reduceTask(state: ProjectState, type: string, p: Payload, at: string): ProjectState {
  const taskId = str(p.task_id);
  switch (type) {
    case "task.created": {
      if (!taskId) return state;
      const task = {
        id: taskId,
        phase_run: "",
        external_id: str(p.external_id) ?? "",
        kind: (str(p.kind) as "feature" | "fix") ?? "feature",
        parent: str(p.parent_id),
        iteration: num(p.iteration) ?? 1,
        max_iterations: state.tasks[taskId]?.max_iterations ?? 3,
        title: str(p.title) ?? "",
        description: "",
        acceptance: [],
        depends_on: list<string>(p.depends_on),
        estimate: (str(p.estimate) as "S" | "M" | "L") ?? "M",
        assigned_role: str(p.assigned_role) ?? "developer",
        assigned_agent: null,
        status: "pending" as TaskStatus,
        branch: null,
        order: Object.keys(state.tasks).length,
        current_step: null,
        result: null,
        created_at: at,
        cost: null,
      };
      return { ...state, tasks: { ...state.tasks, [taskId]: { ...task, ...state.tasks[taskId] } } };
    }
    case "task.updated":
      return patchTask(state, taskId, (p.changes as Partial<Task>) ?? {});
    case "task.ready":
      return patchTask(state, taskId, { status: "ready" });
    case "task.started":
      return patchTask(state, taskId, {
        status: "in_progress",
        branch: str(p.branch),
        iteration: num(p.iteration) ?? 1,
        assigned_agent: str(p.agent_id),
        current_step: "developer",
      });
    case "task.step.completed": {
      const step = str(p.step) ?? "";
      const verdict = str(p.verdict);
      const status = step === "tester" && verdict === "pass" ? undefined : TASK_STEP_STATUS[step];
      return patchTask(state, taskId, { current_step: step, ...(status ? { status } : {}) });
    }
    case "task.iteration":
      return patchTask(state, taskId, {
        iteration: num(p.iteration) ?? 1,
        max_iterations: num(p.max_iterations) ?? 3,
        status: "in_progress",
      });
    case "task.completed":
      return patchTask(state, taskId, {
        status: "done",
        cost: money(p.cost),
        current_step: null,
      });
    case "task.escalated":
      return patchTask(state, taskId, { status: "escalated" });
    case "task.cancelled":
      return patchTask(state, taskId, { status: "cancelled" });
    default:
      return state;
  }
}

function reduceGate(state: ProjectState, event: EventEnvelope, p: Payload): ProjectState {
  const gateId = str(p.gate_id);
  if (!gateId) return state;
  if (event.type === "gate.opened") {
    const gate: GateView = {
      id: gateId,
      type: (str(p.type) as GateView["type"]) ?? "approval",
      key: state.gates[gateId]?.key ?? "",
      phaseRunId: null,
      phaseId: str(p.phase_id),
      taskId: str(p.task_id),
      title: str(p.title) ?? "",
      summary: str(p.summary) ?? "",
      artifacts: list(p.artifacts),
      questions: state.gates[gateId]?.questions ?? [],
      reason: state.gates[gateId]?.reason ?? null,
      status: "open",
      openedAt: event.created_at,
      decision: null,
      decidedBy: null,
      decidedAt: null,
    };
    const next = { ...state, gates: { ...state.gates, [gateId]: gate } };
    const phase = gate.phaseId ? state.phases[gate.phaseId] : undefined;
    return phase && (phase.status === "running" || phase.status === "reopened")
      ? patchPhase(next, gate.phaseId, { status: "waiting_gate" })
      : next;
  }
  const current = state.gates[gateId];
  if (!current) return state;
  if (event.type === "gate.decided" || event.type === "question.answered") {
    const by = p.decided_by as { name?: string } | null | undefined;
    const decided: GateView = {
      ...current,
      status: event.type === "question.answered" ? "answered" : "decided",
      decision: str(p.decision) ?? current.decision,
      decidedBy: by?.name ?? event.actor.name ?? current.decidedBy,
      decidedAt: event.created_at,
    };
    const next = { ...state, gates: { ...state.gates, [gateId]: decided } };
    const phase = current.phaseId ? state.phases[current.phaseId] : undefined;
    return phase?.status === "waiting_gate"
      ? patchPhase(next, current.phaseId, { status: "running" })
      : next;
  }
  if (event.type === "gate.expired") {
    return { ...state, gates: { ...state.gates, [gateId]: { ...current, status: "expired" } } };
  }
  return state;
}

function reduceAgent(state: ProjectState, event: EventEnvelope, p: Payload): ProjectState {
  const agentId = str(p.agent_id);
  switch (event.type) {
    case "agent.hired": {
      if (!agentId) return state;
      const avatar = p.avatar as { color?: string } | undefined;
      const agents = {
        ...state.agents,
        [agentId]: {
          id: agentId,
          role: str(p.role) ?? "agent",
          displayName: str(p.display_name) ?? str(p.role) ?? "Agent",
          room: str(p.room) ?? IDLE_ROOM,
          status: "idle" as const,
          color: avatar?.color,
          turnId: null,
          purpose: null,
          lastToolAt: null,
          ...(state.agents[agentId] ? { status: state.agents[agentId].status } : {}),
        },
      };
      return { ...state, agents, rooms: computeRooms(agents) };
    }
    case "agent.released":
      return patchAgent(state, agentId, { status: "released" });
    case "agent.moved":
      return patchAgent(state, agentId, { room: str(p.to_room) ?? IDLE_ROOM });
    case "agent.status":
      return patchAgent(state, agentId, {
        status: (str(p.status) as AgentView["status"]) ?? "idle",
      });
    case "agent.turn.started":
      return patchAgent(state, agentId, {
        status: "working",
        turnId: str(p.turn_id),
        purpose: str(p.purpose),
        room: str(p.room) ?? state.agents[agentId ?? ""]?.room ?? IDLE_ROOM,
      });
    case "agent.turn.completed":
    case "agent.turn.failed": {
      const next = addArtifacts(state, p.artifacts, event, null);
      const speaking = { ...next.speaking };
      if (agentId) delete speaking[agentId];
      return patchAgent({ ...next, speaking }, agentId, { turnId: null, purpose: null });
    }
    case "agent.tool.used": {
      const owner = Object.values(state.agents).find((a) => a.turnId === str(p.turn_id));
      return owner ? patchAgent(state, owner.id, { lastToolAt: event.created_at }) : state;
    }
    default:
      return state;
  }
}

function reduceBudget(state: ProjectState, type: string, p: Payload): ProjectState {
  switch (type) {
    case "budget.warning":
      return {
        ...state,
        budget: { ...state.budget, warning: true, spent: num(p.spent) ?? state.budget.spent },
      };
    case "budget.exceeded":
      return {
        ...state,
        budget: {
          ...state.budget,
          warning: false,
          exceeded: true,
          spent: num(p.spent) ?? state.budget.spent,
        },
      };
    case "budget.org_warning":
      return { ...state, budget: { ...state.budget, orgWarning: true } };
    case "budget.org_exceeded":
      return { ...state, budget: { ...state.budget, orgExceeded: true } };
    default:
      return state;
  }
}

function addSpend(state: ProjectState, p: Payload): ProjectState {
  const cost = num(p.cost);
  if (cost === null) return state;
  const spent = state.budget.spent + cost;
  const next = patchProject(state, { spent: spent.toFixed(6) });
  return {
    ...next,
    budget: {
      ...budgetFlags(next, next.budget.budget, spent),
      orgWarning: state.budget.orgWarning,
      orgExceeded: state.budget.orgExceeded,
    },
  };
}

export function applyEvent(state: ProjectState, event: EventEnvelope): ProjectState {
  if (state.projectId && event.project_id !== state.projectId) return state;
  if (!isKnownType(event.type)) {
    console.debug(`[dexterhouse] ignored unknown event type ${event.type}`);
    return { ...state, unknownEvents: state.unknownEvents + 1 };
  }
  if (state.events.some((e) => e.id === event.id)) return state;
  const p = event.payload ?? {};
  let next = state;
  const family = event.type.split(".")[0];
  if (family === "project") next = reduceProject(next, event.type, p);
  else if (family === "process" || family === "phase") {
    next = reducePhase(next, event.type, p, event.created_at);
    if (event.type === "phase.step.completed") {
      next = addArtifacts(next, p.artifacts, event, str(p.phase_id));
    }
  } else if (family === "task") next = reduceTask(next, event.type, p, event.created_at);
  else if (family === "gate" || family === "question") next = reduceGate(next, event, p);
  else if (family === "agent") {
    next = reduceAgent(next, event, p);
    if (event.type === "agent.turn.completed") next = addSpend(next, p);
  } else if (family === "budget") next = reduceBudget(next, event.type, p);
  const events = [...next.events, event];
  if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS);
  return { ...next, events, lastEventId: event.id };
}

export function applySpeaking(state: ProjectState, speech: Speech): ProjectState {
  const current = state.speaking[speech.agentId];
  if (current && current.turnId === speech.turnId && current.seq >= speech.seq) return state;
  // The server sends the last ~280 characters of the turn each time: replace, never append.
  return { ...state, speaking: { ...state.speaking, [speech.agentId]: speech } };
}

/** Older events loaded over REST for the log: added to `events` only, the state is untouched
 * (the snapshot already includes their effects). */
export function mergeHistory(state: ProjectState, history: EventEnvelope[]): ProjectState {
  const seen = new Set(state.events.map((e) => e.id));
  const older = history.filter(
    (e) =>
      !seen.has(e.id) &&
      isKnownType(e.type) &&
      (!state.projectId || e.project_id === state.projectId),
  );
  if (older.length === 0) return state;
  const events = [...older, ...state.events].sort(
    (a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id),
  );
  return { ...state, events: events.slice(-MAX_EVENTS) };
}
