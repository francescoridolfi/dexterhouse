// SPDX-License-Identifier: AGPL-3.0-or-later
// Replay timeline (F-015): events in order, idle gaps (a gate waiting for a human) shortened
// to 10 s so that 1×–20× stays watchable; gate markers.
import type { EventEnvelope } from "../../api/types.ts";

export const MAX_GAP_MS = 10_000;

export interface Timeline {
  events: EventEnvelope[];
  /** Playback time (ms from the first event) of each event. */
  times: number[];
  /** Wall time (ms since epoch) of each event. */
  wall: number[];
  duration: number;
  /** Indices of `gate.opened` events. */
  gates: number[];
}

export function buildTimeline(input: EventEnvelope[]): Timeline {
  const seen = new Set<string>();
  const events = [...input]
    .filter((e) => !seen.has(e.id) && seen.add(e.id))
    .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
  const wall = events.map((e) => Date.parse(e.created_at));
  const times: number[] = [];
  wall.forEach((at, i) => {
    const previous = i === 0 ? at : wall[i - 1]!;
    times.push(i === 0 ? 0 : times[i - 1]! + Math.min(Math.max(at - previous, 0), MAX_GAP_MS));
  });
  const gates = events.flatMap((e, i) => (e.type === "gate.opened" ? [i] : []));
  return { events, times, wall, duration: times.at(-1) ?? 0, gates };
}

/** How many events have happened at playback time `t` (binary search). */
export function countAt(timeline: Timeline, t: number): number {
  let lo = 0;
  let hi = timeline.times.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (timeline.times[mid]! <= t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Playback time of the last event at or before a wall time (Log row → replay). */
export function timeAtWall(timeline: Timeline, wallMs: number): number {
  let index = -1;
  timeline.wall.forEach((at, i) => {
    if (at <= wallMs) index = i;
  });
  return index < 0 ? 0 : timeline.times[index]!;
}

export function nextGate(timeline: Timeline, t: number, direction: 1 | -1): number | null {
  const times = timeline.gates.map((i) => timeline.times[i]!);
  const found =
    direction === 1 ? times.find((g) => g > t + 1) : [...times].reverse().find((g) => g < t - 1);
  return found ?? null;
}
