// SPDX-License-Identifier: AGPL-3.0-or-later
import { create } from "zustand";

import type { EventEnvelope, Snapshot } from "../api/types.ts";
import { type Connection, type ProjectState, type Speech, emptyState } from "./model.ts";
import { applyEvent, applySnapshot, applySpeaking, mergeHistory } from "./reducer.ts";

export interface ProjectStore extends ProjectState {
  connection: Connection;
  reset: (projectId: string | null) => void;
  snapshot: (snapshot: Snapshot) => void;
  event: (event: EventEnvelope) => void;
  history: (events: EventEnvelope[]) => void;
  speak: (speech: Speech) => void;
  setConnection: (connection: Connection) => void;
}

/** The single domain store read by the 2D views and the 3D office (frontend.md). */
export const useProjectStore = create<ProjectStore>()((set) => ({
  ...emptyState(),
  connection: "idle",
  reset: (projectId) => {
    set({ ...emptyState(projectId), connection: "idle" });
  },
  snapshot: (snapshot) => {
    set((state) => applySnapshot(state, snapshot));
  },
  event: (event) => {
    set((state) => applyEvent(state, event));
  },
  history: (events) => {
    set((state) => mergeHistory(state, events));
  },
  speak: (speech) => {
    set((state) => applySpeaking(state, speech));
  },
  setConnection: (connection) => {
    set({ connection });
  },
}));
