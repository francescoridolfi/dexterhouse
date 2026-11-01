// SPDX-License-Identifier: AGPL-3.0-or-later
// Static geometry as instance lists (one draw call per shape): floors, walls, furniture, chairs.
import { type FloorGrid, GRID } from "./grid.ts";
import { type Facing, MANIFEST, type OfficePlan, PLAN, type Prop, type Shape } from "./plan.ts";

export interface Instance {
  shape: Shape;
  /** Centre of the instance, metres (x = grid x, z = grid y). */
  x: number;
  y: number;
  z: number;
  sx: number;
  sy: number;
  sz: number;
  rotY: number;
  /** Hex colour, or `floor:<room>` / `wall` resolved by the palette. */
  color: string;
}

export const WALL_HEIGHT = 0.7;
const WALL_THICKNESS = 0.3;
const FACING_ROT: Record<Facing, number> = { S: 0, E: Math.PI / 2, N: Math.PI, W: -Math.PI / 2 };

function propInstances(prop: Prop, rotY: number): Instance[] {
  const model = MANIFEST.models[prop.model];
  if (!model) return [];
  const w = prop.w ?? 1;
  const h = prop.h ?? 1;
  const cx = prop.x + w / 2;
  const cz = prop.y + h / 2;
  const cos = Math.cos(rotY);
  const sin = Math.sin(rotY);
  return model.parts.map((part) => {
    const ox = part.at[0] * w;
    const oz = part.at[2] * h;
    return {
      shape: part.shape,
      x: cx + ox * cos + oz * sin,
      y: part.at[1] + part.size[1] / 2,
      z: cz - ox * sin + oz * cos,
      sx: part.size[0] * w,
      sy: part.size[1],
      sz: part.size[2] * h,
      rotY,
      color: part.color,
    };
  });
}

function wallInstances(grid: FloorGrid): Instance[] {
  const out: Instance[] = [];
  const used = new Uint8Array(grid.w * grid.h);
  const wall = (x: number, y: number) =>
    x >= 0 && y >= 0 && x < grid.w && y < grid.h && grid.walls[y * grid.w + x] === 1;
  const box = (x: number, z: number, sx: number, sz: number): Instance => ({
    shape: "box",
    x,
    y: WALL_HEIGHT / 2,
    z,
    sx,
    sy: WALL_HEIGHT,
    sz,
    rotY: 0,
    color: "wall",
  });
  for (let y = 0; y < grid.h; y++) {
    for (let x = 0; x < grid.w;) {
      let end = x;
      while (wall(end, y)) end++;
      if (end - x >= 2) {
        out.push(box((x + end) / 2, y + 0.5, end - x, WALL_THICKNESS));
        for (let i = x; i < end; i++) used[y * grid.w + i] = 1;
      }
      x = end === x ? x + 1 : end;
    }
  }
  for (let x = 0; x < grid.w; x++) {
    for (let y = 0; y < grid.h;) {
      let end = y;
      let fresh = false;
      for (; wall(x, end); end++) if (!used[end * grid.w + x]) fresh = true;
      if (fresh) {
        out.push(box(x + 0.5, (y + end) / 2, WALL_THICKNESS, end - y));
      }
      y = end === y ? y + 1 : end;
    }
  }
  return out;
}

export function staticInstances(plan: OfficePlan = PLAN, grid: FloorGrid = GRID): Instance[] {
  const out: Instance[] = [];
  for (const room of plan.rooms) {
    const { x, y, w, h } = room.rect;
    out.push({
      shape: "box",
      x: x + w / 2,
      y: -0.05,
      z: y + h / 2,
      sx: w,
      sy: 0.1,
      sz: h,
      rotY: 0,
      color: `floor:${room.id}`,
    });
    for (const prop of room.props) out.push(...propInstances(prop, (prop.rot * Math.PI) / 180));
    for (const seat of room.seats) {
      // The chair back sits behind the agent, who faces `seat.facing`.
      const chair: Prop = { model: "dh/chair", x: seat.x, y: seat.y, rot: 0 };
      out.push(...propInstances(chair, FACING_ROT[seat.facing]));
    }
  }
  out.push(...wallInstances(grid));
  return out;
}
