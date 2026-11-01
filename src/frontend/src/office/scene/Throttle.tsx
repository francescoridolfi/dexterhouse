// SPDX-License-Identifier: AGPL-3.0-or-later
// While a 2D tab is active the canvas is on demand: render a few frames per second so that the
// scene keeps up with the state (NFR-P3). Nothing runs while the page is hidden.
import { useThree } from "@react-three/fiber";
import { useEffect } from "react";

export function Throttle({ running, fps }: { running: boolean; fps: number }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => invalidate(), 1000 / fps);
    return () => window.clearInterval(timer);
  }, [running, fps, invalidate]);
  return null;
}
