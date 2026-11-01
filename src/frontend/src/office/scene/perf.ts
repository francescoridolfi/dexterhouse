// SPDX-License-Identifier: AGPL-3.0-or-later
// Fallback rule (NFR-P3, ux_3d_office.md): under 20 fps for 10 s → switch to the 2D view.
export const MIN_FPS = 20;
export const SLOW_FOR_S = 10;
export const WARMUP_S = 3;

export interface FrameStats {
  frames: number;
  fps: number;
  frameMs: number[];
  /** Last frame's draw calls and triangles (budget: 150 and 400 k). */
  calls: number;
  triangles: number;
}

declare global {
  interface Window {
    __dhOffice?: FrameStats;
  }
}

/** Pure check, unit tested: a window of per-second fps samples → should we fall back? */
export function tooSlow(samples: number[], min = MIN_FPS, seconds = SLOW_FOR_S): boolean {
  return samples.length >= seconds && samples.slice(-seconds).every((fps) => fps < min);
}
