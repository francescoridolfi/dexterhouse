// SPDX-License-Identifier: AGPL-3.0-or-later
// Hover tooltip for avatars and objects (ux_3d_office.md, "Interazioni").
import { useLayoutEffect, useRef } from "react";

import { useRuntime } from "../scene/context.ts";

export function Tooltip() {
  const hover = useRuntime((s) => s.hover);
  const el = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (el.current && hover)
      el.current.style.transform = `translate(${hover.x + 14}px, ${hover.y + 14}px)`;
  }, [hover]);
  if (!hover) return null;
  return (
    <div
      ref={el}
      role="tooltip"
      className="pointer-events-none fixed top-0 left-0 z-30 max-w-72 rounded-card border border-line bg-surface px-2 py-1 text-xs whitespace-pre-line shadow-card"
    >
      {hover.text}
    </div>
  );
}
