// SPDX-License-Identifier: AGPL-3.0-or-later
// Context documents and change requests shaped like docs/specs (E-13).
import type { ChangeRequest, ContextDocument } from "../api/e13.ts";
import { PROJECT_ID } from "./fixtures.ts";

export function contextDoc(
  overrides: Partial<ContextDocument["data"]> & { id?: string; content?: string } = {},
): ContextDocument {
  const { id = "doc-1", content, ...data } = overrides;
  return {
    id,
    project: PROJECT_ID,
    kind: "context",
    name: "analysis-pdf",
    version: 1,
    content_hash: "h",
    phase_run: null,
    produced_by: { role: null, turn_id: null },
    created_at: "2026-11-01T10:00:00Z",
    content,
    data: {
      filename: "analysis.pdf",
      mime: "application/pdf",
      size: 52_224,
      sha256: "abc",
      status: "processed",
      active: true,
      uploaded_by: "u",
      change_request: null,
      chars: 4200,
      pages: 3,
      truncated: false,
      ...data,
    },
  };
}

export function changeRequest(overrides: Partial<ChangeRequest> = {}): ChangeRequest {
  return {
    id: "cr-1",
    project: PROJECT_ID,
    number: 1,
    title: "Add waiting list",
    body: "When a course is full, users join a **waiting list**.",
    budget: "15.00",
    status: "draft",
    created_by: "u",
    started_at: null,
    completed_at: null,
    created_at: "2026-11-02T10:00:00Z",
    cost: null,
    release: null,
    ...overrides,
  };
}

export const user = (role: "viewer" | "member" | "admin", id = "u") => ({
  id,
  username: role,
  email: "",
  display_name: role,
  organizations: [{ slug: "default", name: "Default", role }],
});

export const page = <T>(results: T[]) => ({ results, next: null, previous: null });
