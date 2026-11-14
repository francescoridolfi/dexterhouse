// SPDX-License-Identifier: AGPL-3.0-or-later
// TanStack Query hooks: server state that is not part of the live project store.
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "./client.ts";
import { api, type ProjectFilters } from "./endpoints.ts";

export const keys = {
  me: ["me"] as const,
  meta: ["meta"] as const,
  projects: (filters: ProjectFilters) => ["projects", filters] as const,
  project: (id: string) => ["project", id] as const,
  openGates: ["gates", "open"] as const,
  gate: (id: string) => ["gate", id] as const,
  projectGates: (id: string) => ["project", id, "gates"] as const,
  artifacts: (id: string, q: string) => ["project", id, "artifacts", q] as const,
  artifact: (id: string) => ["artifact", id] as const,
  versions: (id: string) => ["artifact", id, "versions"] as const,
  diff: (id: string, against: number) => ["artifact", id, "diff", against] as const,
  codeTree: (id: string, ref: string) => ["project", id, "code", "tree", ref] as const,
  codeFile: (id: string, ref: string, path: string) =>
    ["project", id, "code", "file", ref, path] as const,
  codeLog: (id: string, ref: string) => ["project", id, "code", "log", ref] as const,
  codeLocation: (id: string) => ["project", id, "code", "location"] as const,
  notes: (id: string) => ["project", id, "notes"] as const,
  agents: (id: string) => ["project", id, "agents"] as const,
  turns: (id: string) => ["project", id, "turns"] as const,
  turn: (id: string) => ["turn", id] as const,
  events: (id: string, params: Record<string, string | undefined>) =>
    ["project", id, "events", params] as const,
  costs: (id: string) => ["project", id, "costs"] as const,
  llmCalls: (id: string) => ["project", id, "llm-calls"] as const,
  task: (id: string) => ["task", id] as const,
  organization: ["organization"] as const,
  members: ["members"] as const,
  orgBudget: ["organization", "budget"] as const,
  orgUsage: (month: string) => ["organization", "usage", month] as const,
  profiles: ["model-profiles"] as const,
  providers: ["providers"] as const,
  estimate: (process: string, chars: number) => ["estimate", process, chars] as const,
};

export const isAuthError = (error: unknown) =>
  error instanceof ApiError && (error.status === 401 || error.status === 403);

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: api.me,
    retry: (count, error) => !isAuthError(error) && count < 2,
    staleTime: 60_000,
  });
}

export function useMeta() {
  return useQuery({ queryKey: keys.meta, queryFn: api.meta, staleTime: 300_000 });
}

/** Open gates of the organization: inbox and header badge (polled until the org WS exists). */
export function useOpenGates() {
  return useQuery({ queryKey: keys.openGates, queryFn: api.openGates, refetchInterval: 15_000 });
}

export function useProjects(filters: ProjectFilters) {
  return useQuery({
    queryKey: keys.projects(filters),
    queryFn: () => api.projects(filters),
    refetchInterval: 15_000,
  });
}
