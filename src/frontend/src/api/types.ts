// SPDX-License-Identifier: AGPL-3.0-or-later
// Wire types of the core REST v1 and WebSocket (contracts/api, contracts/events). Money is a
// decimal string in EUR; dates are ISO 8601 strings.

export type ProjectStatus =
  "draft" | "running" | "waiting" | "paused" | "completed" | "failed" | "archived";
export type WaitingReason = "gate" | "budget" | "provider" | "workspace";
export type ExecutionMode = "supervised" | "autonomous";
export type PhaseStatus =
  | "pending"
  | "ready"
  | "running"
  | "waiting_gate"
  | "reopened"
  | "completed"
  | "failed"
  | "skipped";
export type TaskStatus =
  | "pending"
  | "ready"
  | "in_progress"
  | "in_review"
  | "in_test"
  | "done"
  | "escalated"
  | "cancelled";
export type GateType = "approval" | "question" | "escalation";
export type GateStatus =
  | "open"
  | "approved"
  | "rejected"
  | "approved_with_comments"
  | "answered"
  | "auto_approved"
  | "expired";
export type AgentStatus = "idle" | "working" | "blocked" | "released";

export interface Page<T> {
  results: T[];
  next: string | null;
  previous: string | null;
}

export interface Project {
  id: string;
  organization: string;
  name: string;
  slug: string;
  status: ProjectStatus;
  waiting_reason: WaitingReason | null;
  execution_mode: ExecutionMode;
  process: { name: string; version: string };
  budget: string;
  spent: string;
  spent_unpriced_tokens: number;
  data_residency: "any" | "local";
  delivery_mode: "push_main" | "pull_request";
  remote_repo_url: string | null;
  remote_token: string | null;
  gate_overrides: Record<string, string>;
  open_gates_count: number;
  current_phases: string[];
  created_by: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  brief?: string;
}

export interface GatePayload {
  title: string;
  summary: string;
  artifacts: ArtifactRef[];
  questions?: Question[];
  attempts?: Attempt[];
  reason?: string | null;
  round?: number;
}

export interface Question {
  id: string;
  text: string;
  kind?: "text" | "choice" | "boolean";
  options?: string[];
  default_assumption?: string;
}

export interface Attempt {
  iteration?: number;
  step?: string;
  verdict?: string;
  summary?: string;
  [key: string]: unknown;
}

export interface Gate {
  id: string;
  project: string;
  phase_run: string;
  task: string | null;
  gate_id: string;
  type: GateType;
  status: GateStatus;
  payload: GatePayload;
  decision: string | null;
  comment: string | null;
  answers: { question_id: string; answer: string }[] | null;
  decided_by: { id: string; name: string } | null;
  opened_at: string;
  decided_at: string | null;
  expires_at: string | null;
  artifacts?: Artifact[];
  next?: string;
}

export interface Phase {
  id: string;
  phase_id: string;
  status: PhaseStatus;
  stage: string;
  current_step: number;
  round: number;
  reopen_count: number;
  exit_attempts: number;
  room: string;
  agents: { role: string; agent_id: string }[];
  gate: Gate | null;
  error_code: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Task {
  id: string;
  phase_run: string;
  external_id: string;
  kind: "feature" | "fix";
  parent: string | null;
  iteration: number;
  max_iterations: number;
  title: string;
  description: string;
  acceptance: string[];
  depends_on: string[];
  estimate: "S" | "M" | "L";
  assigned_role: string;
  assigned_agent: string | null;
  status: TaskStatus;
  branch: string | null;
  order: number;
  current_step: string | null;
  result: unknown;
  created_at: string;
}

export interface SnapshotAgent {
  agent_id: string;
  role: string;
  display_name: string;
  room: string;
  status: AgentStatus;
  avatar: { model?: string; color?: string } | Record<string, unknown>;
}

export interface Snapshot {
  type: "snapshot";
  project: Project;
  phases: Phase[];
  tasks: Task[];
  gates_open: Gate[];
  agents: SnapshotAgent[];
  workspace: unknown;
  budget: { budget: string; spent: string; unpriced_tokens?: number; currency?: string };
  last_event_id: string | null;
}

export interface Actor {
  type: "agent" | "user" | "system";
  id: string | null;
  name?: string;
}

export interface EventEnvelope {
  id: string;
  type: string;
  schema_version: number;
  organization_id: string;
  project_id: string;
  actor: Actor;
  correlation_id: string;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface SpeakingMessage {
  type: "speaking";
  agent_id: string;
  turn_id: string;
  text: string;
  seq: number;
}

export type ServerMessage =
  | Snapshot
  | { type: "event"; event: EventEnvelope }
  | SpeakingMessage
  | { type: "heartbeat"; server_time: string }
  | { type: "error"; code: string; detail: string };

export interface ArtifactRef {
  id: string;
  kind: string;
  version: number;
}

export interface Artifact {
  id: string;
  project: string;
  kind: string;
  name: string;
  version: number;
  content_hash: string;
  phase_run: string | null;
  produced_by: { role: string | null; turn_id: string | null };
  created_at: string;
  content?: string;
  data?: unknown;
}

export interface Note {
  id: string;
  project: string;
  author: string;
  phase_run: string | null;
  content: string;
  consumed: boolean;
  created_at: string;
}

export interface Agent {
  id: string;
  project: string;
  role: string;
  display_name: string;
  package: { name: string; version: string };
  placeholder: boolean;
  source: "builtin" | "marketplace" | "local";
  model_profile: string;
  allowed_tools: string[];
  room: string;
  avatar: Record<string, unknown>;
  status: AgentStatus;
  turns_count: number;
  spent: string;
  hired_at: string | null;
  released_at: string | null;
}

export interface ToolCall {
  seq: number;
  tool: string;
  arguments: Record<string, unknown>;
  allowed: boolean;
  status: "pending" | "done" | "error" | "denied";
  denied_reason: string | null;
  duration_ms: number;
  result_excerpt: string | null;
  truncated: boolean;
}

export interface Turn {
  id: string;
  agent: string;
  phase_run: string | null;
  task: string | null;
  step: string;
  status: string;
  purpose: string;
  tool_calls_count: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  cost: string;
  profile_used: string;
  attempt: number;
  error_code: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  context_manifest?: Record<string, unknown>;
  messages?: unknown[];
  output?: unknown;
  error_detail?: string | null;
  tool_calls?: ToolCall[];
}

export interface TokenCost {
  cost: string;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
}

export interface Estimate {
  low: number;
  high: number;
  basis: "static" | "history";
  currency: "EUR";
}

export interface ProjectCosts {
  currency: "EUR";
  budget: string;
  spent: string;
  unpriced_tokens: number;
  estimate: Estimate;
  by_phase: (TokenCost & {
    phase_run: string | null;
    phase_id: string | null;
    calls: number;
    turns: number;
  })[];
  by_agent: (TokenCost & {
    agent_id: string | null;
    role: string | null;
    display_name: string | null;
    calls: number;
    turns: number;
  })[];
  by_task: (TokenCost & { task_id: string; external_id: string })[];
  by_provider: (TokenCost & {
    provider: string;
    model: string;
    calls: number;
    errors: number;
    avg_latency_ms: number | null;
  })[];
  by_day: { day: string; calls: number; cost: string }[];
}

export interface LLMCall {
  id: string;
  agent_turn: string | null;
  provider: string;
  model: string;
  profile: string;
  status: string;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  cost: string | null;
  price_version: string;
  latency_ms: number;
  error_detail: string | null;
  trace_id: string;
  created_at: string;
}

export interface User {
  id: string;
  username: string;
  email: string;
  display_name: string;
  organizations: { slug: string; name: string; role: Role }[];
}

export type Role = "owner" | "admin" | "member" | "viewer";

export interface Organization {
  id: string;
  slug: string;
  name: string;
  settings: Record<string, unknown>;
  budget_monthly: string | null;
  spent_month: string;
}

export interface Member {
  id: string;
  user: { id: string; username: string };
  role: Role;
  created_at: string;
}

export interface OrgBudget {
  currency: "EUR";
  budget_monthly: string | null;
  spent_month: string;
  month: string;
}

export interface OrgUsage {
  month: string;
  currency: "EUR";
  spent: string;
  budget_monthly: string | null;
  calls: number;
  tokens: { input: number; output: number; cached: number };
  projects: { project_id: string; name: string; calls: number; cost: string }[];
  by_day: { day: string; calls: number; cost: string }[];
}

export interface ModelProfile {
  profile: "strong" | "balanced" | "fast" | "embed";
  configured: boolean;
  source: "organization" | "default" | null;
  provider: string | null;
  model: string | null;
  base_url: string;
  api_key_env: string | null;
  api_key: string | null;
  needs_key: boolean;
  is_local: boolean;
  options: Record<string, unknown>;
}

export interface ProviderInfo {
  id: string;
  local: boolean;
  needs_key: boolean;
  key_set: boolean;
  binary_found?: boolean;
  base_url?: string;
}

export interface Meta {
  version: string;
  providers: string[];
  processes: {
    name: string;
    version: string;
    phases: { id: string; agent: string }[];
    requirements: Record<string, string[]>;
  }[];
  "3d_enabled": boolean;
  features: Record<string, boolean>;
}

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  errors?: { field: string; message: string }[];
}
