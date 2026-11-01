// SPDX-License-Identifier: AGPL-3.0-or-later
// One function per REST v1 endpoint used by the dashboard.
import { getJson, patchJson, postJson, putJson, query, request } from "./client.ts";
import type {
  Agent,
  Artifact,
  Estimate,
  EventEnvelope,
  Gate,
  LLMCall,
  Member,
  Meta,
  ModelProfile,
  Note,
  OrgBudget,
  OrgUsage,
  Organization,
  Page,
  Project,
  ProjectCosts,
  ProviderInfo,
  Snapshot,
  Task,
  Turn,
  User,
} from "./types.ts";

const V1 = "/api/v1";

export interface ProjectFilters {
  status?: string;
  execution_mode?: string;
  q?: string;
}

export interface NewProject {
  name: string;
  brief: string;
  process?: string;
  execution_mode: "supervised" | "autonomous";
  budget: string;
  remote_repo_url?: string | null;
  remote_token?: string | null;
  delivery_mode?: "push_main" | "pull_request";
  data_residency?: "any" | "local";
}

export interface DecideBody {
  decision?: string;
  comment?: string;
  answers?: { question_id: string; answer: string }[];
}

export const api = {
  csrf: () => getJson<{ detail: string }>(`${V1}/auth/csrf`),
  login: (username: string, password: string) =>
    postJson<User>(`${V1}/auth/login`, { username, password }),
  logout: () => postJson<undefined>(`${V1}/auth/logout`),
  me: () => getJson<User>(`${V1}/auth/me`),
  meta: () => getJson<Meta>(`${V1}/meta`),

  projects: (filters: ProjectFilters = {}, cursor?: string) =>
    getJson<Page<Project>>(cursor ?? `${V1}/projects${query({ ...filters, limit: 100 })}`),
  project: (id: string) => getJson<Project>(`${V1}/projects/${id}`),
  createProject: (body: NewProject) => postJson<Project>(`${V1}/projects`, body),
  updateProject: (id: string, body: Partial<NewProject>) =>
    patchJson<Project>(`${V1}/projects/${id}`, body),
  projectAction: (id: string, action: "start" | "pause" | "resume" | "retry") =>
    postJson<Project>(`${V1}/projects/${id}/${action}`),
  snapshot: (id: string) => getJson<Snapshot>(`${V1}/projects/${id}/snapshot`),
  estimate: (process: string, briefChars: number) =>
    getJson<Estimate>(`${V1}/estimate${query({ process, brief_chars: briefChars })}`),

  tasks: (id: string) => getJson<Page<Task>>(`${V1}/projects/${id}/tasks?limit=200`),
  task: (id: string) => getJson<Task & { children: Task[] }>(`${V1}/tasks/${id}`),
  cancelTask: (id: string) => postJson<Task>(`${V1}/tasks/${id}/cancel`),
  gate: (id: string) => getJson<Gate>(`${V1}/gates/${id}`),
  openGates: () => getJson<Page<Gate>>(`${V1}/gates?status=open&limit=200`),
  projectGates: (id: string) => getJson<Page<Gate>>(`${V1}/projects/${id}/gates?limit=200`),
  decide: (id: string, body: DecideBody) => postJson<Gate>(`${V1}/gates/${id}/decide`, body),

  artifacts: (id: string, params: { kind?: string; q?: string } = {}) =>
    getJson<Page<Artifact>>(`${V1}/projects/${id}/artifacts${query({ ...params, limit: 200 })}`),
  artifact: (id: string) => getJson<Artifact>(`${V1}/artifacts/${id}`),
  artifactVersions: (id: string) =>
    getJson<{ results: Artifact[] }>(`${V1}/artifacts/${id}/versions`),
  artifactDiff: (id: string, against: number) =>
    getJson<{ from: number; to: number; diff: string }>(
      `${V1}/artifacts/${id}/diff${query({ against })}`,
    ),

  notes: (id: string) => getJson<Page<Note>>(`${V1}/projects/${id}/notes`),
  addNote: (id: string, content: string, phaseRun: string | null) =>
    postJson<Note>(`${V1}/projects/${id}/notes`, { content, phase_run: phaseRun }),

  agents: (id: string) => getJson<{ results: Agent[] }>(`${V1}/projects/${id}/agents`),
  turns: (id: string, params: { status?: string } = {}) =>
    getJson<Page<Turn>>(`${V1}/projects/${id}/turns${query({ ...params, limit: 100 })}`),
  turn: (id: string) => getJson<Turn>(`${V1}/turns/${id}`),
  events: (id: string, params: Record<string, string | undefined> = {}, cursor?: string) =>
    getJson<Page<EventEnvelope>>(
      cursor ?? `${V1}/projects/${id}/events${query({ ...params, limit: 500 })}`,
    ),

  recentEvents: (id: string) =>
    getJson<Page<EventEnvelope>>(`${V1}/projects/${id}/events?limit=200&order=desc`),
  costs: (id: string) => getJson<ProjectCosts>(`${V1}/projects/${id}/costs`),
  llmCalls: (id: string, cursor?: string) =>
    getJson<Page<LLMCall>>(cursor ?? `${V1}/projects/${id}/llm-calls?limit=25`),

  organization: () => getJson<Organization>(`${V1}/organization`),
  updateOrganization: (body: Partial<Pick<Organization, "name" | "settings">>) =>
    patchJson<Organization>(`${V1}/organization`, body),
  members: () => getJson<{ results: Member[] }>(`${V1}/organization/members`),
  orgBudget: () => getJson<OrgBudget>(`${V1}/organization/budget`),
  setOrgBudget: (budget: string | null) =>
    putJson<OrgBudget>(`${V1}/organization/budget`, { budget_monthly: budget }),
  orgUsage: (month?: string) => getJson<OrgUsage>(`${V1}/organization/usage${query({ month })}`),
  modelProfiles: () => getJson<{ results: ModelProfile[] }>(`${V1}/model-profiles`),
  saveModelProfile: (profile: string, body: Record<string, unknown>) =>
    putJson<ModelProfile>(`${V1}/model-profiles/${profile}`, body),
  providers: () => getJson<{ results: ProviderInfo[] }>(`${V1}/providers`),
  packages: () => request<unknown>("GET", `${V1}/packages`),
};
