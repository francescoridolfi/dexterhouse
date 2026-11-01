// SPDX-License-Identifier: AGPL-3.0-or-later
// Wall clock for durations on screen, refreshed every second (0 until the first tick).
import { useEffect, useState } from "react";

export function useNow(everyMs = 1_000): number {
  const [now, setNow] = useState(0);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = window.setTimeout(tick, 0);
    const timer = window.setInterval(tick, everyMs);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [everyMs]);
  return now;
}
