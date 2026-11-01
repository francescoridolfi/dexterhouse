// SPDX-License-Identifier: AGPL-3.0-or-later
// Inside the canvas: projects every avatar head to the screen and moves its DOM label (one
// pass per frame, CSSOM only: the CSP forbids inline style attributes). Labels only within
// a distance of the view centre, unless zoomed in or selected.
import { useFrame } from "@react-three/fiber";
import { Vector3 } from "three";

import { BREAK_ROOM_LIMIT } from "../avatars/visible.ts";
import { roomById, roomCenter } from "../rooms/plan.ts";
import { useOffice } from "../scene/context.ts";

const RADIUS = [11, 18, Infinity];
const BREAK = roomCenter(roomById("break_room")!);
const v = new Vector3();

/** CSSOM only (the CSP forbids inline style attributes). */
function moveLabel(
  el: HTMLElement,
  ndc: Vector3,
  size: { width: number; height: number },
  show: boolean,
) {
  const sx = ((ndc.x + 1) / 2) * size.width;
  const sy = ((1 - ndc.y) / 2) * size.height;
  const visible = show && sx > -50 && sy > -50 && sx < size.width + 50 && sy < size.height + 50;
  el.style.display = visible ? "block" : "none";
  if (visible) el.style.transform = `translate(${sx.toFixed(1)}px, ${sy.toFixed(1)}px)`;
}

export function OverlaySync() {
  const { runtime, motion, labels } = useOffice();
  useFrame(({ camera, size }) => {
    const { camera: view, selected, model } = runtime.getState();
    const radius = RADIUS[view.zoom] ?? Infinity;
    const centre = view.follow ? motion.get(view.follow) : undefined;
    const cx = centre?.x ?? view.target.x;
    const cz = centre?.z ?? view.target.z;
    const place = (el: HTMLElement, x: number, y: number, z: number, show: boolean) =>
      moveLabel(el, v.set(x, y, z).project(camera), size, show);
    for (const [id, el] of labels) {
      if (id === "break_room") {
        const resting = Object.values(model.avatars).filter(
          (a) => a.room === "break_room" && !a.walking,
        );
        place(el, BREAK.x, 2, BREAK.y, resting.length > BREAK_ROOM_LIMIT);
        continue;
      }
      const rt = motion.get(id);
      if (!rt) {
        moveLabel(el, v.set(0, 0, 0), { width: 0, height: 0 }, false);
        continue;
      }
      const near = Math.hypot(rt.x - cx, rt.z - cz) <= radius || id === selected;
      place(el, rt.x, 1.55, rt.z, near && rt.opacity > 0.5);
    }
  });
  return null;
}
