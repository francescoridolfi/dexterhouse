// SPDX-License-Identifier: AGPL-3.0-or-later
// The office reads two stores: the project state (live store or replay store) and its runtime.
import { createContext, useContext } from "react";
import { useStore } from "zustand";
import type { StoreApi } from "zustand/vanilla";

import type { ProjectState } from "../../store/model.ts";
import type { AvatarRuntime } from "../avatars/motion.ts";
import type { OfficeRuntime, OfficeRuntimeStore } from "./runtime.ts";

export interface OfficeContextValue {
  project: StoreApi<ProjectState>;
  runtime: OfficeRuntimeStore;
  /** Mutable per-frame avatar positions (never in React state). */
  motion: Map<string, AvatarRuntime>;
  /** DOM label per avatar id (plus "break_room" for the overflow counter), moved per frame. */
  labels: Map<string, HTMLElement>;
  /** Scene clock in ms: performance.now() live, the playback time in replay. */
  clock: () => number;
  /** Wall time in ms of what is on screen: Date.now() live, the current event in replay. */
  wallTime: () => number;
  replay: boolean;
  /** Motion speed multiplier: the replay speed (walks keep up with 20×), 1 live. */
  timeScale: () => number;
  actions: OfficeActions;
}

/** What clicks in the scene open: always the 2D panels and tabs (NFR-U3). */
export interface OfficeActions {
  openGate: (gateId: string) => void;
  openCosts: () => void;
  openArtifact: (artifactId: string) => void;
  openTask: (taskId: string) => void;
  openPackages: () => void;
  openOverview: () => void;
}

export const OfficeContext = createContext<OfficeContextValue | null>(null);

export function useOffice(): OfficeContextValue {
  const value = useContext(OfficeContext);
  if (!value) throw new Error("useOffice outside <OfficeContext>");
  return value;
}

export function useProject<T>(selector: (state: ProjectState) => T): T {
  return useStore(useOffice().project, selector);
}

export function useRuntime<T>(selector: (state: OfficeRuntime) => T): T {
  return useStore(useOffice().runtime, selector);
}
