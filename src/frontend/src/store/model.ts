// SPDX-License-Identifier: AGPL-3.0-or-later
// Normalised project state shared by the 2D dashboard and the 3D office (frontend.md).
// Built from the WebSocket `snapshot` plus events; views only read it.
import type {
  AgentStatus,
  ArtifactRef,
  EventEnvelope,
  ExecutionMode,
  GateStatus,
  GateType,
  PhaseStatus,
  Project,
  Question,
  Task,
} from "../api/types.ts";

export interface AgentView {
  id: string;
  role: string;
  displayName: string;
  room: string;
  status: AgentStatus;
  color?: string;
  turnId: string | null;
  purpose: string | null;
  lastToolAt: string | null;
}

export interface PhaseView {
  phaseId: string;
  runId: string | null;
  status: PhaseStatus;
  room: string;
  needs: string[];
  currentStep: number;
  round: number;
  startedAt: string | null;
  finishedAt: string | null;
  durationS: number | null;
  cost: string | null;
  agents: string[];
}

export type TaskView = Task & { cost: string | null };

export interface GateView {
  id: string;
  type: GateType;
  key: string;
  phaseRunId: string | null;
  phaseId: string | null;
  taskId: string | null;
  title: string;
  summary: string;
  artifacts: ArtifactRef[];
  questions: Question[];
  reason: string | null;
  status: GateStatus | "decided";
  openedAt: string;
  decision: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
}

export interface ArtifactView extends ArtifactRef {
  phaseId: string | null;
  agentId: string | null;
  at: string;
}

export interface Speech {
  agentId: string;
  turnId: string;
  text: string;
  seq: number;
}

export interface BudgetView {
  budget: number;
  spent: number;
  warning: boolean;
  exceeded: boolean;
  orgWarning: boolean;
  orgExceeded: boolean;
}

export type Connection = "idle" | "connecting" | "live" | "reconnecting" | "offline";

export interface ProjectState {
  projectId: string | null;
  project: Project | null;
  mode: ExecutionMode | null;
  phases: Record<string, PhaseView>;
  phaseOrder: string[];
  tasks: Record<string, TaskView>;
  gates: Record<string, GateView>;
  agents: Record<string, AgentView>;
  /** room id → agent ids currently in it (what the 3D office renders). */
  rooms: Record<string, string[]>;
  artifacts: Record<string, ArtifactView>;
  events: EventEnvelope[];
  speaking: Record<string, Speech>;
  budget: BudgetView;
  lastEventId: string | null;
  snapshotLoaded: boolean;
  unknownEvents: number;
}

export const MAX_EVENTS = 2_000;
export const IDLE_ROOM = "break_room";

export function emptyState(projectId: string | null = null): ProjectState {
  return {
    projectId,
    project: null,
    mode: null,
    phases: {},
    phaseOrder: [],
    tasks: {},
    gates: {},
    agents: {},
    rooms: {},
    artifacts: {},
    events: [],
    speaking: {},
    budget: {
      budget: 0,
      spent: 0,
      warning: false,
      exceeded: false,
      orgWarning: false,
      orgExceeded: false,
    },
    lastEventId: null,
    snapshotLoaded: false,
    unknownEvents: 0,
  };
}
