// SPDX-License-Identifier: AGPL-3.0-or-later
// "Reduce transparency", as on macOS: backdrop blur is cheap on a GPU but is re-rendered on the
// CPU every frame when WebGL runs in software (SwiftShader, llvmpipe), which starves the 3D
// office. Then, or when the user asks for less transparency, glass becomes opaque panels.
import { hasWebGL2 } from "./webgl.ts";

const SOFTWARE = /swiftshader|llvmpipe|softpipe|software|basic render/i;

/** WebGL 2 works, but only in software: the browser refuses a context without a perf caveat. */
export function softwareWebGL(): boolean {
  if (!hasWebGL2()) return false;
  try {
    const canvas = document.createElement("canvas");
    const fast = canvas.getContext("webgl2", { failIfMajorPerformanceCaveat: true });
    if (!fast) return true;
    const info = fast.getExtension("WEBGL_debug_renderer_info");
    const renderer = String(
      fast.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : fast.RENDERER) ?? "",
    );
    fast.getExtension("WEBGL_lose_context")?.loseContext();
    return SOFTWARE.test(renderer);
  } catch {
    return false;
  }
}

export function applyGlassMode(): void {
  const reduce =
    window.matchMedia?.("(prefers-reduced-transparency: reduce)").matches === true ||
    softwareWebGL();
  if (reduce) document.documentElement.dataset.glass = "reduced";
}
