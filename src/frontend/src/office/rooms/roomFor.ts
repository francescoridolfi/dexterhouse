// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase/agent room → plan room: unknown rooms fall back to the open space with one warning.
import type { ProjectState } from "../../store/model.ts";
import { type RoomDef, roomById } from "./plan.ts";

export const FALLBACK_ROOM = "open_space";
const warned = new Set<string>();

export function resolveRoom(id: string | null | undefined): RoomDef {
  const room = id ? roomById(id) : undefined;
  if (room) return room;
  if (id && !warned.has(id)) {
    warned.add(id);
    console.warn(`[dexterhouse] room "${id}" is not in office.json: using ${FALLBACK_ROOM}`);
  }
  return roomById(FALLBACK_ROOM)!;
}

const LIVE = new Set(["running", "waiting_gate", "reopened"]);

/** Rooms whose phase is in progress (their light is on), from `phases[].room`. */
export function litRooms(state: ProjectState): Map<string, string> {
  const lit = new Map<string, string>();
  for (const id of state.phaseOrder) {
    const phase = state.phases[id];
    if (phase && LIVE.has(phase.status)) lit.set(resolveRoom(phase.room).id, phase.phaseId);
  }
  return lit;
}

/** The room to frame when the office opens: reception with an open gate, else the phase. */
export function initialRoom(state: ProjectState): string {
  if (Object.values(state.gates).some((g) => g.status === "open")) return "reception";
  return litRooms(state).keys().next().value ?? "reception";
}
