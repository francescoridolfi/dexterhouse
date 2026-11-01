// SPDX-License-Identifier: AGPL-3.0-or-later
// Where bound props sit (centre of their footprint, metres) and the shared hover handlers.
import type { ThreeEvent } from "@react-three/fiber";

import { type Bind, PLAN, type Prop } from "../rooms/plan.ts";
import type { OfficeRuntimeStore } from "../scene/runtime.ts";

export interface Anchor {
  room: string;
  prop: Prop;
  x: number;
  z: number;
}

export function anchors(bind: Bind): Anchor[] {
  return PLAN.rooms.flatMap((room) =>
    room.props
      .filter((prop) => prop.bind === bind)
      .map((prop) => ({
        room: room.id,
        prop,
        x: prop.x + (prop.w ?? 1) / 2,
        z: prop.y + (prop.h ?? 1) / 2,
      })),
  );
}

export function anchor(bind: Bind, room?: string): Anchor {
  const found = anchors(bind).find((a) => !room || a.room === room);
  if (!found) throw new Error(`no ${bind} prop${room ? ` in ${room}` : ""}`);
  return found;
}

/** Tooltip handlers: `text` is computed on hover (instance id for instanced meshes). */
export function hoverHandlers(
  runtime: OfficeRuntimeStore,
  text: (instanceId: number | undefined) => string | null,
) {
  return {
    onPointerMove: (event: ThreeEvent<PointerEvent>) => {
      event.stopPropagation();
      const value = text(event.instanceId);
      runtime
        .getState()
        .setHover(
          value
            ? { text: value, x: event.nativeEvent.clientX, y: event.nativeEvent.clientY }
            : null,
        );
      document.body.style.cursor = value ? "pointer" : "";
    },
    onPointerOut: () => {
      runtime.getState().setHover(null);
      document.body.style.cursor = "";
    },
  };
}
