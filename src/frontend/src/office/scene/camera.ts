// SPDX-License-Identifier: AGPL-3.0-or-later
// Isometric orthographic camera (CD-035): 4 orientations, 3 zoom levels, pan within the plan.
import { PLAN } from "../rooms/plan.ts";

export const ELEVATION = Math.atan(1 / Math.SQRT2);
export const DISTANCE = 80;
export const ZOOM_FACTORS = [1, 1.8, 3] as const;

export interface Ground {
  x: number;
  z: number;
}

/** Camera azimuth for orientation 0..3 (0 looks from the south-east corner). */
export function azimuth(orientation: number): number {
  return Math.PI / 4 + (orientation * Math.PI) / 2;
}

export function cameraOffset(az: number): [number, number, number] {
  const flat = Math.cos(ELEVATION) * DISTANCE;
  return [Math.sin(az) * flat, Math.sin(ELEVATION) * DISTANCE, Math.cos(az) * flat];
}

/** Pixels per metre that fit the whole plan in a viewport of `width` × `height`. */
export function fitZoom(width: number, height: number): number {
  const span = Math.hypot(PLAN.grid.w, PLAN.grid.h);
  return Math.max(4, Math.min(width / span, height / (span * Math.sin(ELEVATION) + 4)));
}

/** World movement for a drag of (dx, dy) pixels: the floor follows the pointer. */
export function panDelta(az: number, zoom: number, dx: number, dy: number): Ground {
  const right = { x: Math.cos(az), z: -Math.sin(az) };
  const away = { x: -Math.sin(az), z: -Math.cos(az) };
  const along = -dx / zoom;
  const depth = dy / (zoom * Math.sin(ELEVATION));
  return { x: right.x * along + away.x * depth, z: right.z * along + away.z * depth };
}

/** Keyboard pan (WASD): one step in screen directions, in metres. */
export function keyPan(az: number, key: string, step = 2): Ground | null {
  const dirs: Record<string, [number, number]> = { w: [0, -1], s: [0, 1], a: [-1, 0], d: [1, 0] };
  const dir = dirs[key];
  if (!dir) return null;
  const right = { x: Math.cos(az), z: -Math.sin(az) };
  const away = { x: -Math.sin(az), z: -Math.cos(az) };
  return {
    x: (right.x * dir[0] - away.x * dir[1]) * step,
    z: (right.z * dir[0] - away.z * dir[1]) * step,
  };
}

export function clampTarget(target: Ground): Ground {
  return {
    x: Math.min(Math.max(target.x, 0), PLAN.grid.w),
    z: Math.min(Math.max(target.z, 0), PLAN.grid.h),
  };
}
