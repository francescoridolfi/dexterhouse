// SPDX-License-Identifier: AGPL-3.0-or-later
// What the office shows on top of the project store: avatar positions and timers, object
// states. Built only from events (live or replay) by the pure `reduceOffice`.
import type { Cell, Seat } from "../rooms/plan.ts";

export type AvatarMode =
  "idle" | "walking" | "working" | "blocked" | "failed" | "handoff" | "celebrate" | "leaving";

export type ToolIcon = "read" | "write" | "exec" | "tests" | "marketplace" | "other";

export interface AvatarModel {
  id: string;
  /** Where the agent is (truth): an existing plan room. */
  room: string;
  cell: Cell;
  seat: Seat | null;
  /** First position when the avatar appears (spawn, HR office or seat). */
  origin: Cell;
  /** Hand-off walk to the next step's room, then back to `room`. */
  errand: { room: string; cell: Cell } | null;
  walking: boolean;
  /** A turn started mid-walk: walk twice as fast (the animation never delays the truth). */
  hurry: boolean;
  working: boolean;
  turnId: string | null;
  purpose: string | null;
  /** Gate id, "security" or "status" while blocked. */
  blockedBy: string | null;
  leaving: boolean;
  tool: ToolIcon | null;
  toolUntil: number;
  failedUntil: number;
  alarmUntil: number;
  celebrateUntil: number;
  /** Replay bubble: the turn summary when the event carries one, else its purpose. */
  summary: string | null;
  summaryUntil: number;
  bornAt: number;
}

export interface DocumentModel {
  id: string;
  kind: string;
  version: number;
  room: string;
  phaseId: string | null;
}

export type PcState = "off" | "on" | "standby";
export type TestLight = "off" | "running" | "pass" | "fail";
export type DockState = "off" | "prepared" | "delivered" | "failed";

export interface OfficeModel {
  avatars: Record<string, AvatarModel>;
  folder: "reception" | "archive";
  bellRingUntil: number;
  packageBox: { state: "arriving" | "installed" | "rejected"; name: string } | null;
  pcs: PcState;
  testLight: { state: TestLight; detail: string | null; reportId: string | null };
  dock: { state: DockState; detail: string | null };
  confettiUntil: number;
  documents: Record<string, DocumentModel>;
}

export const TIMERS = {
  tool: 1_500,
  failed: 3_000,
  alarm: 3_000,
  celebrate: 2_000,
  confetti: 4_000,
  bell: 4_000,
  summary: 4_000,
} as const;

export function emptyOffice(): OfficeModel {
  return {
    avatars: {},
    folder: "reception",
    bellRingUntil: 0,
    packageBox: null,
    pcs: "off",
    testLight: { state: "off", detail: null, reportId: null },
    dock: { state: "off", detail: null },
    confettiUntil: 0,
    documents: {},
  };
}
