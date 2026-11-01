// SPDX-License-Identifier: AGPL-3.0-or-later
// Domain state (Zustand) shared by the dashboard and the 3D office; see store/README.md.
export * from "./model.ts";
export {
  applyEvent,
  applySnapshot,
  applySpeaking,
  gateFromRest,
  isKnownType,
  mergeHistory,
} from "./reducer.ts";
export * from "./selectors.ts";
export { useProjectStore, type ProjectStore } from "./projectStore.ts";
export { ProjectSocket, type SocketHandlers } from "./socket.ts";
