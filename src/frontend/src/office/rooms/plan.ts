// SPDX-License-Identifier: AGPL-3.0-or-later
// The floor plan (ux/office_layout.md): 40 × 30 cells of 1 m, origin top left, x right, y down.
import manifestJson from "../assets/manifest.json";
import officeJson from "./office.json";

export const ROOM_IDS = [
  "reception",
  "archive",
  "meeting_room",
  "design_studio",
  "hr_office",
  "pm_office",
  "open_space",
  "review_corner",
  "qa_lab",
  "break_room",
  "release_dock",
] as const;
export type RoomId = (typeof ROOM_IDS)[number];

export const BINDS = [
  "phase_light",
  "test_light",
  "bell",
  "budget_lamp",
  "kanban",
  "package_box",
  "dock_light",
  "workspace_pc",
  "documents",
] as const;
export type Bind = (typeof BINDS)[number];

export type Facing = "N" | "E" | "S" | "W";

export interface Cell {
  x: number;
  y: number;
}

export interface Seat extends Cell {
  facing: Facing;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Prop extends Cell {
  model: string;
  rot: number;
  w?: number;
  h?: number;
  bind?: Bind;
}

export interface RoomDef {
  id: RoomId;
  label: { en: string; it: string };
  rect: Rect;
  capacity: number;
  doors: Cell[];
  seats: Seat[];
  props: Prop[];
  light: { color_token: string; bind: Bind };
}

export interface OfficePlan {
  schema: 1;
  grid: { w: number; h: number; cell_m: number };
  rooms: RoomDef[];
  walls: string;
  spawn: Cell;
  exit: Cell;
}

export type Shape = "box" | "cyl";

export interface ModelPart {
  shape: Shape;
  size: [number, number, number];
  at: [number, number, number];
  color: string;
}

export interface ModelDef {
  bind?: Bind;
  walkable?: boolean;
  parts: ModelPart[];
}

export interface AssetManifest {
  schema: 1;
  models: Record<string, ModelDef>;
}

export const PLAN = officeJson as OfficePlan;
export const MANIFEST = manifestJson as unknown as AssetManifest;

const BY_ID = new Map(PLAN.rooms.map((room) => [room.id as string, room]));

export function roomById(id: string): RoomDef | undefined {
  return BY_ID.get(id);
}

/** Interior cells of a room: its rect minus the top row and left column (its walls). */
export function interior(rect: Rect, grid = PLAN.grid): Rect {
  const right = Math.min(rect.x + rect.w, grid.w - 1);
  const bottom = Math.min(rect.y + rect.h, grid.h - 1);
  return { x: rect.x + 1, y: rect.y + 1, w: right - rect.x - 1, h: bottom - rect.y - 1 };
}

export function roomCenter(room: RoomDef): Cell {
  const inner = interior(room.rect);
  return { x: inner.x + inner.w / 2, y: inner.y + inner.h / 2 };
}

export function inRect(rect: Rect, cell: Cell): boolean {
  return (
    cell.x >= rect.x && cell.x < rect.x + rect.w && cell.y >= rect.y && cell.y < rect.y + rect.h
  );
}
