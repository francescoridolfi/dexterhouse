// SPDX-License-Identifier: AGPL-3.0-or-later
// Per-frame avatar motion (pure): A* path at 1.4 cells/s (×2 in a hurry), or a teleport with
// a fade when motion is reduced. Returns true once the avatar reaches its goal.
import { type FloorGrid, GRID } from "../rooms/grid.ts";
import { key } from "../rooms/occupancy.ts";
import type { Cell, Facing } from "../rooms/plan.ts";
import type { AvatarModel } from "../state/model.ts";
import { findPath } from "../utils/pathfinding.ts";

export const WALK_SPEED = 1.4;
const FADE_S = 0.2;

export interface AvatarRuntime {
  x: number;
  z: number;
  heading: number;
  path: Cell[];
  step: number;
  goal: string;
  opacity: number;
  /** Seconds left of the teleport fade (out, jump, in) or of the exit fade. */
  fade: number;
  anim: number;
  moving: boolean;
}

const FACING: Record<Facing, number> = { S: 0, E: Math.PI / 2, N: Math.PI, W: -Math.PI / 2 };

export function goalOf(avatar: AvatarModel): Cell {
  return avatar.errand?.cell ?? avatar.cell;
}

export function seatHeading(avatar: AvatarModel): number | null {
  return avatar.seat && !avatar.walking && !avatar.errand ? FACING[avatar.seat.facing] : null;
}

export function startMotion(avatar: AvatarModel): AvatarRuntime {
  return {
    x: avatar.origin.x + 0.5,
    z: avatar.origin.y + 0.5,
    heading: avatar.seat ? FACING[avatar.seat.facing] : 0,
    path: [],
    step: 0,
    goal: key(avatar.origin),
    opacity: 0,
    fade: 0,
    anim: Math.random() * 10,
    moving: false,
  };
}

function plan(rt: AvatarRuntime, goal: Cell, grid: FloorGrid): void {
  const from = { x: Math.floor(rt.x), y: Math.floor(rt.z) };
  rt.path = findPath(grid, from, goal) ?? [];
  rt.step = 1;
  rt.goal = key(goal);
}

function jump(rt: AvatarRuntime, goal: Cell): void {
  rt.x = goal.x + 0.5;
  rt.z = goal.y + 0.5;
  rt.path = [];
}

/** Advance one frame. `teleport` = reduced motion / fast mode. */
export function stepMotion(
  rt: AvatarRuntime,
  avatar: AvatarModel,
  dt: number,
  teleport: boolean,
  grid: FloorGrid = GRID,
): boolean {
  rt.anim += dt;
  const goal = goalOf(avatar);
  if (rt.fade > 0) {
    // Teleport: fade out, jump at half time, fade in.
    const before = rt.fade;
    rt.fade = Math.max(0, rt.fade - dt);
    if (before > FADE_S && rt.fade <= FADE_S && !avatar.leaving) jump(rt, goal);
    rt.opacity = avatar.leaving ? rt.fade / (2 * FADE_S) : Math.abs(rt.fade - FADE_S) / FADE_S;
    return rt.fade === 0 && avatar.walking;
  }
  rt.opacity = Math.min(1, rt.opacity + dt / 0.4);
  if (!avatar.walking) {
    rt.moving = false;
    const seated = seatHeading(avatar);
    if (seated !== null) rt.heading = seated;
    return false;
  }
  if (rt.goal !== key(goal) || rt.path.length === 0) {
    plan(rt, goal, grid);
    if (teleport || rt.path.length === 0) {
      rt.fade = 2 * FADE_S;
      rt.moving = false;
      return false;
    }
  }
  const speed = WALK_SPEED * (avatar.hurry ? 2 : 1);
  let budget = speed * dt;
  while (budget > 0 && rt.step < rt.path.length) {
    const next = rt.path[rt.step]!;
    const tx = next.x + 0.5;
    const tz = next.y + 0.5;
    const dist = Math.hypot(tx - rt.x, tz - rt.z);
    if (dist > 1e-6) rt.heading = Math.atan2(tx - rt.x, tz - rt.z);
    if (dist <= budget) {
      rt.x = tx;
      rt.z = tz;
      budget -= dist;
      rt.step += 1;
    } else {
      rt.x += ((tx - rt.x) / dist) * budget;
      rt.z += ((tz - rt.z) / dist) * budget;
      budget = 0;
    }
  }
  rt.moving = rt.step < rt.path.length;
  if (rt.moving) return false;
  if (avatar.leaving) {
    rt.fade = 2 * FADE_S;
    return false;
  }
  rt.path = [];
  return true;
}
