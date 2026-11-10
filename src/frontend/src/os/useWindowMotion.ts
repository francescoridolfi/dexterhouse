// SPDX-License-Identifier: AGPL-3.0-or-later
// Window motion (Web Animations, compositor-only transforms):
// - zoom / restore: FLIP from the previous box to the new one;
// - minimize: shrink into the app's dock tile; restore: grow back out of it.
// Animation styles override the class ones while they run, so the window stays visible
// during the minimize even though the store already marked it `invisible`.
import { type RefObject, useLayoutEffect, useRef } from "react";

import type { AppId } from "./apps.ts";

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

const ZOOM_MS = 380;
const GENIE_MS = 420;
const SPRING = "cubic-bezier(0.3, 1.25, 0.45, 1)";
const SMOOTH = "cubic-bezier(0.32, 0.72, 0, 1)";

function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

// offset* ignore transforms, so a box measured mid-animation is still the layout box.
function boxOf(el: HTMLElement): Box {
  return { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight };
}

/** Transform that maps the element (at its layout box) onto the dock tile of `app`. */
function toDock(el: HTMLElement, app: AppId): string {
  const tile =
    document.querySelector<HTMLElement>(`[data-tile="${app}"]`) ??
    document.querySelector<HTMLElement>("nav[data-dock]");
  const box = boxOf(el);
  const target = tile?.getBoundingClientRect() ?? {
    left: window.innerWidth / 2 - 24,
    top: window.innerHeight - 60,
    width: 48,
    height: 48,
  };
  const scale = Math.max(0.04, target.width / Math.max(box.w, 1));
  const dx = target.left + target.width / 2 - (box.x + box.w / 2);
  const dy = target.top + target.height / 2 - (box.y + box.h / 2);
  return `translate(${dx}px, ${dy}px) scale(${scale})`;
}

export function useWindowMotion(
  ref: RefObject<HTMLElement | null>,
  app: AppId,
  maximized: boolean,
  minimized: boolean,
) {
  const last = useRef<Box | null>(null);
  const was = useRef({ maximized, minimized });

  // Runs before the "remember the box" effect below, so `last` is still the old box.
  useLayoutEffect(() => {
    const el = ref.current;
    const prev = was.current;
    was.current = { maximized, minimized };
    if (!el || reducedMotion()) return;

    if (prev.minimized !== minimized) {
      const docked = toDock(el, app);
      const shown = { transform: "none", opacity: 1, visibility: "visible" };
      const hidden = { transform: docked, opacity: 0, visibility: "visible" };
      el.animate(minimized ? [shown, hidden] : [hidden, shown], {
        duration: GENIE_MS,
        easing: minimized ? "cubic-bezier(0.55, 0, 0.75, 0.2)" : SMOOTH,
      });
      return;
    }

    const from = last.current;
    if (prev.maximized !== maximized && from) {
      const to = boxOf(el);
      if (to.w === 0 || to.h === 0) return;
      const first = `translate(${from.x - to.x}px, ${from.y - to.y}px) scale(${from.w / to.w}, ${from.h / to.h})`;
      el.animate(
        [
          { transformOrigin: "0 0", transform: first },
          { transformOrigin: "0 0", transform: "none" },
        ],
        {
          duration: ZOOM_MS,
          easing: SPRING,
        },
      );
    }
  }, [ref, app, maximized, minimized]);

  useLayoutEffect(() => {
    if (ref.current && !minimized) last.current = boxOf(ref.current);
  });
}
