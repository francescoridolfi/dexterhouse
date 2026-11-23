// SPDX-License-Identifier: AGPL-3.0-or-later
// E-13 wire types and endpoints: context documents (docs/specs/context-documents.md) and
// change requests (docs/specs/change-requests.md). Fields marked "assumed" are not fixed by
// the specs yet; the views treat them as optional.
import { ApiError, deleteJson, getJson, patchJson, postForm, postJson, query } from "./client.ts";
import type { Artifact, Estimate, Page } from "./types.ts";

const V1 = "/api/v1";

export type ContextStatus = "processing" | "processed" | "failed";

/** `Artifact.data` of a `context` artifact (projects/services/context.py). */
export interface ContextData {
  filename: string;
  title?: string;
  mime: string;
  size: number;
  sha256: string;
  status: ContextStatus;
  active: boolean;
  /** User id; assumed: the API may expand it to `{id, name}`. */
  uploaded_by: string | { id: string; name: string } | null;
  change_request: string | null;
  error?: string;
  chars?: number;
  pages?: number | null;
  truncated?: boolean;
}

/** One document = the latest version of a `context` artifact; its id is the doc id. */
export interface ContextDocument extends Artifact {
  data: ContextData;
}

export type ChangeRequestStatus =
  "draft" | "queued" | "running" | "completed" | "failed" | "cancelled";

export interface ChangeRequest {
  id: string;
  project: string;
  number: number;
  title: string;
  body: string;
  budget: string;
  status: ChangeRequestStatus;
  created_by: string | { id: string; name: string } | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  /** Assumed: spend of the CR's iteration and its delivery (Costs filter, task 15). */
  cost?: string | null;
  iteration?: number | null;
  release?: { number: number; url: string | null } | null;
}

export interface ChangeRequestInput {
  title: string;
  body: string;
  budget: string;
}

export const e13 = {
  contextDocs: (projectId: string, all = false) =>
    getJson<Page<ContextDocument>>(
      `${V1}/projects/${projectId}/context${query({ all: all ? 1 : undefined })}`,
    ),
  contextDoc: (id: string) => getJson<ContextDocument>(`${V1}/context/${id}`),
  contextDownloadUrl: (id: string) => `${V1}/context/${id}/download`,
  uploadContext: (projectId: string, file: File, changeRequest?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (changeRequest) form.append("change_request", changeRequest);
    return postForm<ContextDocument>(`${V1}/projects/${projectId}/context`, form);
  },
  deactivateContext: (id: string) => deleteJson<ContextDocument | undefined>(`${V1}/context/${id}`),

  changeRequests: (projectId: string) =>
    getJson<Page<ChangeRequest>>(`${V1}/projects/${projectId}/change-requests`),
  createChangeRequest: (projectId: string, body: ChangeRequestInput) =>
    postJson<ChangeRequest>(`${V1}/projects/${projectId}/change-requests`, body),
  updateChangeRequest: (id: string, body: Partial<ChangeRequestInput>) =>
    patchJson<ChangeRequest>(`${V1}/change-requests/${id}`, body),
  changeRequestAction: (id: string, action: "queue" | "cancel") =>
    postJson<ChangeRequest>(`${V1}/change-requests/${id}/${action}`),
  /** Assumed to share the project estimate shape (low/high/basis). */
  estimateChangeRequest: (id: string) => getJson<Estimate>(`${V1}/change-requests/${id}/estimate`),
};

export const e13Keys = {
  context: (projectId: string) => ["project", projectId, "context"] as const,
  contextDoc: (id: string) => ["context", id] as const,
  changeRequests: (projectId: string) => ["project", projectId, "change-requests"] as const,
  crEstimate: (id: string) => ["change-request", id, "estimate"] as const,
};

/** Name for `uploaded_by` / `created_by`: expanded object, "you", or nothing. */
export function personName(
  who: string | { id: string; name: string } | null | undefined,
  meId: string | undefined,
  you: string,
): string {
  if (!who) return "";
  if (typeof who === "object") return who.name;
  return who === meId ? you : "";
}

/** Field-level reason of a refused upload (`validation_failed`), else the message. */
export function uploadReason(error: unknown): string {
  if (error instanceof ApiError) {
    const fields = error.fieldErrors();
    return fields.file ?? Object.values(fields)[0] ?? error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

/** Uploads one after the other (the 20-document limit is checked per file). */
export async function uploadContextFiles(
  projectId: string,
  files: File[],
  changeRequest?: string,
): Promise<{ name: string; reason: string }[]> {
  const failed: { name: string; reason: string }[] = [];
  for (const file of files) {
    try {
      await e13.uploadContext(projectId, file, changeRequest);
    } catch (error) {
      failed.push({ name: file.name, reason: uploadReason(error) });
    }
  }
  return failed;
}
