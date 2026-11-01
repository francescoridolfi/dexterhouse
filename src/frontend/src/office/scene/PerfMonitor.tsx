// SPDX-License-Identifier: AGPL-3.0-or-later
// NFR-P3 fallback: under 20 fps for 10 s in a row the office hands over to the 2D view.
// Also exposes the last frame times on `window.__dhOffice` for the scripted benchmark.
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";

import { WARMUP_S, tooSlow } from "./perf.ts";

export function PerfMonitor({ active, onSlow }: { active: boolean; onSlow: () => void }) {
  const second = useRef({ start: 0, frames: 0 });
  const samples = useRef<number[]>([]);
  const elapsed = useRef(0);
  const fired = useRef(false);

  useFrame((state, dt) => {
    const stats = (window.__dhOffice ??= { frames: 0, fps: 0, frameMs: [] });
    stats.frames += 1;
    stats.frameMs.push(dt * 1000);
    if (stats.frameMs.length > 600) stats.frameMs.splice(0, stats.frameMs.length - 600);
    if (!active || document.hidden) {
      // Throttled (2D tab) or hidden: these frames say nothing about the GPU.
      samples.current = [];
      second.current = { start: state.clock.elapsedTime, frames: 0 };
      return;
    }
    elapsed.current += dt;
    second.current.frames += 1;
    const span = state.clock.elapsedTime - second.current.start;
    if (span >= 1) {
      stats.fps = second.current.frames / span;
      if (elapsed.current > WARMUP_S) samples.current.push(stats.fps);
      if (samples.current.length > 30) samples.current.shift();
      second.current = { start: state.clock.elapsedTime, frames: 0 };
      if (!fired.current && tooSlow(samples.current)) {
        fired.current = true;
        onSlow();
      }
    }
  });
  return null;
}
