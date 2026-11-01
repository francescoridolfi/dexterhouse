// SPDX-License-Identifier: AGPL-3.0-or-later
// Walkable grid: wall cells (RLE in office.json) plus the footprints of blocking props.
import { type Cell, MANIFEST, type OfficePlan, PLAN, type Prop, inRect, interior } from "./plan.ts";

export interface FloorGrid {
  w: number;
  h: number;
  walls: Uint8Array;
  /** 1 = not walkable (wall or furniture). */
  blocked: Uint8Array;
}

/** `rle:a,b,c…`: alternating runs of free and wall cells, row major, starting with free. */
export function decodeWalls(rle: string, w: number, h: number): Uint8Array {
  if (!rle.startsWith("rle:")) throw new Error("walls must start with rle:");
  const runs = rle.slice(4).split(",").map(Number);
  const cells = new Uint8Array(w * h);
  let at = 0;
  runs.forEach((length, i) => {
    if (!Number.isInteger(length) || length < 0) throw new Error(`bad run ${length}`);
    if (i % 2 === 1) cells.fill(1, at, at + length);
    at += length;
  });
  if (at !== w * h) throw new Error(`walls cover ${at} cells, expected ${w * h}`);
  return cells;
}

export function footprint(prop: Prop): Cell[] {
  const cells: Cell[] = [];
  for (let dy = 0; dy < (prop.h ?? 1); dy++)
    for (let dx = 0; dx < (prop.w ?? 1); dx++) cells.push({ x: prop.x + dx, y: prop.y + dy });
  return cells;
}

export function buildGrid(plan: OfficePlan = PLAN): FloorGrid {
  const { w, h } = plan.grid;
  const walls = decodeWalls(plan.walls, w, h);
  const blocked = walls.slice();
  for (const room of plan.rooms) {
    for (const prop of room.props) {
      if (MANIFEST.models[prop.model]?.walkable) continue;
      for (const cell of footprint(prop)) blocked[cell.y * w + cell.x] = 1;
    }
  }
  return { w, h, walls, blocked };
}

export function isFree(grid: FloorGrid, cell: Cell): boolean {
  return (
    cell.x >= 0 &&
    cell.y >= 0 &&
    cell.x < grid.w &&
    cell.y < grid.h &&
    grid.blocked[cell.y * grid.w + cell.x] === 0
  );
}

/** The room whose interior contains the cell (doors and walls belong to none). */
export function roomAt(cell: Cell, plan: OfficePlan = PLAN): string | null {
  const x = Math.floor(cell.x);
  const y = Math.floor(cell.y);
  return plan.rooms.find((room) => inRect(interior(room.rect, plan.grid), { x, y }))?.id ?? null;
}

export const GRID = buildGrid();
