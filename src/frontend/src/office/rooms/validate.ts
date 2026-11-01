// SPDX-License-Identifier: AGPL-3.0-or-later
// Type guard for office.json (schema 1, ux/office_layout.md): returns the list of problems.
import { decodeWalls } from "./grid.ts";
import { type AssetManifest, BINDS, type OfficePlan, ROOM_IDS, inRect, interior } from "./plan.ts";

type Json = Record<string, unknown>;

const isObject = (v: unknown): v is Json => typeof v === "object" && v !== null;
const isInt = (v: unknown): v is number => Number.isInteger(v);
const isCell = (v: unknown): v is Json & { x: number; y: number } =>
  isObject(v) && isInt(v.x) && isInt(v.y);

function checkRoom(room: unknown, plan: Json, manifest: AssetManifest, errors: string[]) {
  if (!isObject(room)) return void errors.push("room is not an object");
  const id = String(room.id);
  const where = `rooms.${id}`;
  if (!(ROOM_IDS as readonly string[]).includes(id)) errors.push(`${where}: unknown room id`);
  const grid = plan.grid as { w: number; h: number; cell_m: number };
  const rect = room.rect as Json;
  if (!isObject(rect) || ![rect.x, rect.y, rect.w, rect.h].every(isInt)) {
    return void errors.push(`${where}: rect must have integer x, y, w, h`);
  }
  const r = rect as unknown as { x: number; y: number; w: number; h: number };
  if (r.x < 0 || r.y < 0 || r.w < 2 || r.h < 2 || r.x + r.w > grid.w || r.y + r.h > grid.h) {
    errors.push(`${where}: rect outside the grid`);
  }
  const seats = Array.isArray(room.seats) ? room.seats : [];
  if (!isInt(room.capacity) || room.capacity > seats.length) {
    errors.push(`${where}: capacity must be ≤ seats.length`);
  }
  const inner = interior(r, grid);
  for (const seat of seats) {
    if (!isCell(seat) || !inRect(inner, seat)) errors.push(`${where}: seat outside the room`);
    else if (!["N", "E", "S", "W"].includes(String((seat as Json).facing))) {
      errors.push(`${where}: seat facing must be N, E, S or W`);
    }
  }
  if (!Array.isArray(room.doors) || room.doors.length === 0 || !room.doors.every(isCell)) {
    errors.push(`${where}: at least one door`);
  }
  for (const prop of Array.isArray(room.props) ? room.props : []) {
    if (!isObject(prop) || !isCell(prop)) {
      errors.push(`${where}: prop needs integer x, y`);
      continue;
    }
    if (!manifest.models[String(prop.model)]) {
      errors.push(`${where}: model ${String(prop.model)} not in the asset manifest`);
    }
    const bind = prop.bind;
    if (
      bind !== undefined &&
      !(typeof bind === "string" && (BINDS as readonly string[]).includes(bind))
    ) {
      errors.push(`${where}: unknown bind ${JSON.stringify(bind)}`);
    }
    const w = isInt(prop.w) ? prop.w : 1;
    const h = isInt(prop.h) ? prop.h : 1;
    if (!inRect(inner, prop) || !inRect(inner, { x: prop.x + w - 1, y: prop.y + h - 1 })) {
      errors.push(`${where}: prop ${String(prop.model)} outside the room`);
    }
  }
  const light = room.light as Json | undefined;
  if (!isObject(light) || light.bind !== "phase_light") errors.push(`${where}: light.bind`);
}

export function validatePlan(value: unknown, manifest: AssetManifest): value is OfficePlan {
  return planErrors(value, manifest).length === 0;
}

export function planErrors(value: unknown, manifest: AssetManifest): string[] {
  const errors: string[] = [];
  if (!isObject(value)) return ["plan is not an object"];
  if (value.schema !== 1) errors.push("schema must be 1");
  const grid = value.grid as Json;
  if (!isObject(grid) || !isInt(grid.w) || !isInt(grid.h)) return [...errors, "grid w, h"];
  const rooms = Array.isArray(value.rooms) ? value.rooms : [];
  const ids = rooms.map((room) => (isObject(room) ? String(room.id) : ""));
  for (const id of ROOM_IDS) if (!ids.includes(id)) errors.push(`missing room ${id}`);
  if (new Set(ids).size !== ids.length) errors.push("duplicate room ids");
  for (const room of rooms) checkRoom(room, value, manifest, errors);
  try {
    decodeWalls(String(value.walls), grid.w, grid.h);
  } catch (error) {
    errors.push(`walls: ${(error as Error).message}`);
  }
  if (!isCell(value.spawn) || !isCell(value.exit)) errors.push("spawn and exit cells");
  return errors;
}
