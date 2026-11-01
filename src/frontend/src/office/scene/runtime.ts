// SPDX-License-Identifier: AGPL-3.0-or-later
// Per-view office runtime: the office model, selection, camera and hover. One instance for
// the live scene, one for the replay; both are fed by the same pure reducers.
import { createStore } from "zustand/vanilla";

import type { EventEnvelope } from "../../api/types.ts";
import type { ProjectState } from "../../store/model.ts";
import { PLAN, roomById, roomCenter } from "../rooms/plan.ts";
import { type OfficeModel, emptyOffice } from "../state/model.ts";
import { arrive, reconcile, reduceOffice } from "../state/reducer.ts";
import { type Ground, clampTarget } from "./camera.ts";

export interface Hover {
  text: string;
  x: number;
  y: number;
}

export interface CameraState {
  orientation: number;
  zoom: number;
  target: Ground;
  follow: string | null;
}

export interface OfficeRuntime {
  model: OfficeModel;
  selected: string | null;
  hover: Hover | null;
  camera: CameraState;
  /** Teleport with fade, no bubbles: `prefers-reduced-motion` or the "fast" toggle. */
  fast: boolean;
  apply: (event: EventEnvelope, state: ProjectState, now: number) => void;
  replace: (model: OfficeModel) => void;
  reconcile: (state: ProjectState, now: number) => void;
  arrive: (agentId: string) => void;
  select: (agentId: string | null) => void;
  setHover: (hover: Hover | null) => void;
  setCamera: (camera: Partial<CameraState>) => void;
  frameRoom: (roomId: string) => void;
  setFast: (fast: boolean) => void;
}

export function createOfficeRuntime(fast = false) {
  return createStore<OfficeRuntime>()((set, get) => ({
    model: emptyOffice(),
    selected: null,
    hover: null,
    camera: {
      orientation: 0,
      zoom: 0,
      target: { x: PLAN.grid.w / 2, z: PLAN.grid.h / 2 },
      follow: null,
    },
    fast,
    apply: (event, state, now) => set({ model: reduceOffice(get().model, event, state, now) }),
    replace: (model) => set({ model }),
    reconcile: (state, now) => {
      const model = reconcile(get().model, state, now);
      if (model !== get().model) set({ model });
    },
    arrive: (agentId) => set({ model: arrive(get().model, agentId) }),
    select: (selected) => set({ selected }),
    setHover: (hover) => set({ hover }),
    setCamera: (camera) => {
      const next = { ...get().camera, ...camera };
      set({ camera: { ...next, target: clampTarget(next.target) } });
    },
    frameRoom: (roomId) => {
      const room = roomById(roomId);
      if (!room) return;
      const c = roomCenter(room);
      get().setCamera({
        target: { x: c.x, z: c.y },
        follow: null,
        zoom: Math.max(get().camera.zoom, 1),
      });
    },
    setFast: (value) => set({ fast: value }),
  }));
}

export type OfficeRuntimeStore = ReturnType<typeof createOfficeRuntime>;
