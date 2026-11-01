// SPDX-License-Identifier: AGPL-3.0-or-later
// WebGL 2 probe before loading the 3D bundle (NFR-U3: without WebGL the 2D is the default).
let cached: boolean | null = null;

export function hasWebGL2(): boolean {
  if (cached !== null) return cached;
  try {
    const canvas = document.createElement("canvas");
    const gl = typeof canvas.getContext === "function" ? canvas.getContext("webgl2") : null;
    cached = !!gl;
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
  } catch {
    cached = false;
  }
  return cached;
}
