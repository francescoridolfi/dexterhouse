// SPDX-License-Identifier: AGPL-3.0-or-later
// Procedural clips of the generic low-poly character (Idle, Walk, Sit + Type, Shrug, Cheer).
import type { AvatarMode } from "../state/model.ts";

export interface Pose {
  /** Vertical offset of the whole body. */
  lift: number;
  /** Leg rotation around x (radians): left, right. */
  legL: number;
  legR: number;
  /** Arm rotation around x and outward around z. */
  armL: number;
  armR: number;
  armOut: number;
  seated: boolean;
}

const STILL: Pose = { lift: 0, legL: 0, legR: 0, armL: 0, armR: 0, armOut: 0, seated: false };

export function pose(mode: AvatarMode, t: number, moving: boolean, seated: boolean): Pose {
  if (moving || mode === "walking" || mode === "handoff" || mode === "leaving") {
    if (!moving) return STILL;
    const swing = Math.sin(t * 9) * 0.6;
    return {
      lift: Math.abs(Math.sin(t * 9)) * 0.04,
      legL: swing,
      legR: -swing,
      armL: -swing * 0.8,
      armR: swing * 0.8,
      armOut: 0,
      seated: false,
    };
  }
  if (mode === "celebrate") {
    return {
      ...STILL,
      lift: Math.abs(Math.sin(t * 6)) * 0.25,
      armL: Math.PI * 0.9,
      armR: Math.PI * 0.9,
      armOut: 0.3,
    };
  }
  if (mode === "failed") {
    return { ...STILL, seated, legL: seated ? -1.5 : 0, legR: seated ? -1.5 : 0, armOut: 0.9 };
  }
  if (mode === "working" && seated) {
    const tap = Math.sin(t * 14) * 0.12;
    return {
      lift: 0,
      legL: -1.5,
      legR: -1.5,
      armL: -1.2 + tap,
      armR: -1.2 - tap,
      armOut: 0,
      seated,
    };
  }
  if (seated) return { ...STILL, legL: -1.5, legR: -1.5, armL: -0.3, armR: -0.3, seated };
  // Idle / blocked standing: a slow sway.
  const sway = Math.sin(t * 1.5) * 0.05;
  return {
    ...STILL,
    armL: sway,
    armR: -sway,
    lift: mode === "working" ? Math.sin(t * 3) * 0.01 : 0,
  };
}
