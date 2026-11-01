// SPDX-License-Identifier: AGPL-3.0-or-later
// Objects moved by events (ux_3d_office.md, "Oggetti e eventi che li muovono"). The bell,
// budget lamp, kanban and room lights read the project store directly.
import type { EventEnvelope } from "../../api/types.ts";
import type { ProjectState } from "../../store/model.ts";
import { resolveRoom } from "../rooms/roomFor.ts";
import { type DocumentModel, type OfficeModel, TIMERS } from "./model.ts";

type Payload = Record<string, unknown>;
type Ref = { id: string; kind: string; version: number };
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const refs = (v: unknown): Ref[] =>
  (Array.isArray(v) ? v : [v]).filter(
    (r): r is Ref => typeof r === "object" && r !== null && typeof (r as Ref).id === "string",
  );

function addDocuments(
  model: OfficeModel,
  items: Ref[],
  room: string,
  phaseId: string | null,
): OfficeModel {
  if (items.length === 0) return model;
  const documents = { ...model.documents };
  for (const ref of items) {
    documents[ref.id] = {
      id: ref.id,
      kind: ref.kind ?? "artifact",
      version: ref.version ?? 1,
      room,
      phaseId: phaseId ?? documents[ref.id]?.phaseId ?? null,
    };
  }
  return { ...model, documents };
}

/** The running phase the agent works in, to know where its documents go at the end. */
function phaseOf(state: ProjectState, agentId: string | null): string | null {
  if (!agentId) return null;
  const running = state.phaseOrder
    .map((id) => state.phases[id])
    .find((p) => p && p.status !== "completed" && p.startedAt && p.agents.includes(agentId));
  return running?.phaseId ?? null;
}

function archive(model: OfficeModel, phaseId: string | null): OfficeModel {
  if (!phaseId) return model;
  const documents: Record<string, DocumentModel> = {};
  for (const [id, doc] of Object.entries(model.documents)) {
    documents[id] = doc.phaseId === phaseId ? { ...doc, room: "archive" } : doc;
  }
  return { ...model, documents };
}

export function reduceObjects(
  model: OfficeModel,
  event: EventEnvelope,
  state: ProjectState,
  now: number,
): OfficeModel {
  const p: Payload = event.payload ?? {};
  switch (event.type) {
    case "project.created":
      return { ...model, folder: "reception" };
    case "project.completed":
    case "project.archived":
      return { ...model, folder: "archive" };
    case "gate.opened":
      return { ...model, bellRingUntil: now + TIMERS.bell };
    case "agent.turn.completed": {
      const agentId = str(p.agent_id);
      const room = model.avatars[agentId ?? ""]?.room ?? "open_space";
      return addDocuments(model, refs(p.artifacts), room, phaseOf(state, agentId));
    }
    case "phase.step.completed": {
      const phaseId = str(p.phase_id);
      const room = resolveRoom(state.phases[phaseId ?? ""]?.room).id;
      return addDocuments(model, refs(p.artifacts), room, phaseId);
    }
    case "task.step.completed": {
      const agentId = str(p.agent_id);
      const room = model.avatars[agentId ?? ""]?.room ?? "open_space";
      return addDocuments(model, refs(p.artifact), room, phaseOf(state, agentId));
    }
    case "phase.completed":
      return archive(model, str(p.phase_id));
    case "package.installing":
      return { ...model, packageBox: { state: "arriving", name: str(p.name) ?? "" } };
    case "package.installed":
      return { ...model, packageBox: { state: "installed", name: str(p.name) ?? "" } };
    case "package.rejected":
      return {
        ...model,
        packageBox: { state: "rejected", name: str(p.name) ?? model.packageBox?.name ?? "" },
      };
    case "workspace.created":
    case "workspace.resumed":
      return { ...model, pcs: "on" };
    case "workspace.idle":
      return { ...model, pcs: "standby" };
    case "workspace.destroyed":
      return { ...model, pcs: "off" };
    case "test.run.started":
      return {
        ...model,
        testLight: { state: "running", detail: str(p.scope), reportId: null },
      };
    case "test.run.completed": {
      const passed = Number(p.passed ?? 0);
      const failed = Number(p.failed ?? 0);
      const report = refs(p.report_artifact)[0];
      return {
        ...model,
        testLight: {
          state: p.ok === false || failed > 0 ? "fail" : "pass",
          detail: `${passed}/${passed + failed}`,
          reportId: report?.id ?? null,
        },
      };
    }
    case "release.prepared":
      return { ...model, dock: { state: "prepared", detail: null } };
    case "release.delivered":
      return {
        ...model,
        dock: { state: "delivered", detail: str(p.pr_url) ?? str(p.remote_url) },
        confettiUntil: now + TIMERS.confetti,
      };
    case "release.failed":
      return { ...model, dock: { state: "failed", detail: str(p.error_code) } };
    default:
      return model;
  }
}
