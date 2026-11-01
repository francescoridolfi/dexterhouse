// SPDX-License-Identifier: AGPL-3.0-or-later
// Shareable clip (F-015): the event sequence as JSON. It holds every event from the start of
// the project to the end of the clip, so that the scene can be rebuilt; `start_at` is where
// playback begins. Video rendering is out of scope.
import type { EventEnvelope } from "../../api/types.ts";

export const CLIP_KIND = "dexterhouse.replay-clip";

export interface Clip {
  kind: typeof CLIP_KIND;
  schema: 1;
  project: { id: string; name: string };
  start_at: string;
  end_at: string;
  exported_at: string;
  events: EventEnvelope[];
}

export function makeClip(
  project: { id: string; name: string },
  events: EventEnvelope[],
  startIndex: number,
  endIndex: number,
): Clip {
  const included = events.slice(0, endIndex + 1);
  return {
    kind: CLIP_KIND,
    schema: 1,
    project,
    start_at: events[startIndex]?.created_at ?? included[0]?.created_at ?? "",
    end_at: included.at(-1)?.created_at ?? "",
    exported_at: new Date().toISOString(),
    events: included,
  };
}

const isEvent = (e: unknown): e is EventEnvelope =>
  typeof e === "object" &&
  e !== null &&
  typeof (e as EventEnvelope).id === "string" &&
  typeof (e as EventEnvelope).type === "string" &&
  typeof (e as EventEnvelope).created_at === "string" &&
  typeof (e as EventEnvelope).payload === "object";

export function parseClip(text: string): Clip {
  const data = JSON.parse(text) as Partial<Clip>;
  if (data.kind !== CLIP_KIND || data.schema !== 1 || !Array.isArray(data.events)) {
    throw new Error("not a DexterHouse replay clip");
  }
  if (!data.events.every(isEvent)) throw new Error("the clip contains malformed events");
  return data as Clip;
}

export function downloadClip(clip: Clip): void {
  const blob = new Blob([JSON.stringify(clip, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${clip.project.name.replace(/[^\w-]+/g, "-").toLowerCase() || "project"}-replay.json`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
