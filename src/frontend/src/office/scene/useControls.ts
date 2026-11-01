// SPDX-License-Identifier: AGPL-3.0-or-later
// Keyboard and pointer controls: Q/E rotate, wheel/pinch/+/- zoom, drag or WASD pan, F follows
// the selected agent (any manual move stops following).
import { type RefObject, useEffect } from "react";

import { ZOOM_FACTORS, azimuth, fitZoom, keyPan, panDelta } from "./camera.ts";
import type { OfficeRuntimeStore } from "./runtime.ts";

const MAX_ZOOM = ZOOM_FACTORS.length - 1;

export function zoomBy(runtime: OfficeRuntimeStore, step: number) {
  const { camera, setCamera } = runtime.getState();
  setCamera({ zoom: Math.min(MAX_ZOOM, Math.max(0, camera.zoom + step)) });
}

export function rotateBy(runtime: OfficeRuntimeStore, step: number) {
  const { camera, setCamera } = runtime.getState();
  setCamera({ orientation: camera.orientation + step });
}

export function followSelected(runtime: OfficeRuntimeStore) {
  const { selected, setCamera } = runtime.getState();
  if (selected) setCamera({ follow: selected });
}

export function useControls(
  element: RefObject<HTMLElement | null>,
  runtime: OfficeRuntimeStore,
  enabled: boolean,
) {
  useEffect(() => {
    const el = element.current;
    if (!el || !enabled) return;
    const pointers = new Map<number, { x: number; y: number }>();
    let pinch = 0;

    const pan = (dx: number, dy: number) => {
      const { camera, setCamera } = runtime.getState();
      const zoom = fitZoom(el.clientWidth, el.clientHeight) * (ZOOM_FACTORS[camera.zoom] ?? 1);
      const move = panDelta(azimuth(camera.orientation), zoom, dx, dy);
      setCamera({
        target: { x: camera.target.x + move.x, z: camera.target.z + move.z },
        follow: null,
      });
    };
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "q") rotateBy(runtime, -1);
      else if (key === "e") rotateBy(runtime, 1);
      else if (key === "f") followSelected(runtime);
      else if (key === "+" || key === "=") zoomBy(runtime, 1);
      else if (key === "-") zoomBy(runtime, -1);
      else {
        const { camera, setCamera } = runtime.getState();
        const move = keyPan(azimuth(camera.orientation), key);
        if (!move) return;
        setCamera({
          target: { x: camera.target.x + move.x, z: camera.target.z + move.z },
          follow: null,
        });
      }
      event.preventDefault();
    };
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      if (Math.abs(event.deltaY) > 4) zoomBy(runtime, event.deltaY < 0 ? 1 : -1);
    };
    const onDown = (event: PointerEvent) => {
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = Math.hypot(a!.x - b!.x, a!.y - b!.y);
      }
    };
    const onMove = (event: PointerEvent) => {
      const last = pointers.get(event.pointerId);
      if (!last) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const distance = Math.hypot(a!.x - b!.x, a!.y - b!.y);
        if (pinch && Math.abs(distance / pinch - 1) > 0.3) {
          zoomBy(runtime, distance > pinch ? 1 : -1);
          pinch = distance;
        }
        return;
      }
      if (event.buttons & 1) pan(event.clientX - last.x, event.clientY - last.y);
    };
    const onUp = (event: PointerEvent) => {
      pointers.delete(event.pointerId);
      if (pointers.size < 2) pinch = 0;
    };
    window.addEventListener("keydown", onKey);
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("pointerdown", onDown);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("keydown", onKey);
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [element, runtime, enabled]);
}
