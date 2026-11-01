// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import type { EventEnvelope } from "../../api/types.ts";
import { project } from "../../test/fixtures.ts";
import { avatarMode } from "../state/mode.ts";
import { makeClip, parseClip } from "./clip.ts";
import { ReplayEngine, emptyReplayState } from "./engine.ts";
import { MAX_GAP_MS, buildTimeline, countAt, nextGate, timeAtWall } from "./timeline.ts";

const T0 = Date.UTC(2026, 10, 1, 10, 0, 0);
let n = 0;
function ev(type: string, payload: Record<string, unknown>, atS: number): EventEnvelope {
  n += 1;
  return {
    id: `e-${String(n).padStart(4, "0")}`,
    type,
    schema_version: 1,
    organization_id: "o",
    project_id: "p-1",
    actor: { type: "system", id: null, name: "system" },
    correlation_id: "c",
    created_at: new Date(T0 + atS * 1000).toISOString(),
    payload,
  };
}

/** A small project: hire, analysis with a gate decided after an hour, then the dev loop. */
function story(): EventEnvelope[] {
  const out = [
    ev("project.created", { name: "GymBook", budget: "20" }, 0),
    ev("process.started", { phases: [{ id: "analysis", needs: [], room: "meeting_room" }] }, 1),
    ev(
      "agent.hired",
      { agent_id: "an", role: "analyst", display_name: "Ada", room: "meeting_room" },
      2,
    ),
    ev("phase.started", { phase_id: "analysis", room: "meeting_room", agents: ["an"] }, 3),
    ev("agent.moved", { agent_id: "an", from_room: "break_room", to_room: "meeting_room" }, 4),
    ev(
      "agent.turn.started",
      { agent_id: "an", turn_id: "t1", room: "meeting_room", purpose: "analysis" },
      5,
    ),
    ev(
      "agent.turn.completed",
      {
        agent_id: "an",
        turn_id: "t1",
        cost: "0.5",
        artifacts: [{ id: "a1", kind: "analysis", version: 1 }],
      },
      30,
    ),
    ev(
      "gate.opened",
      { gate_id: "g1", type: "approval", phase_id: "analysis", title: "Approve" },
      31,
    ),
    ev("gate.decided", { gate_id: "g1", type: "approval", decision: "approve" }, 3_631),
    ev("phase.completed", { phase_id: "analysis", cost: "0.5" }, 3_632),
  ];
  for (let i = 0; i < 450; i++)
    out.push(ev("agent.tool.used", { turn_id: "t2", tool: "fs.read" }, 3_700 + i));
  return out;
}

describe("timeline", () => {
  it("orders, dedupes and shortens idle gaps", () => {
    const events = story();
    const timeline = buildTimeline([...events].reverse().concat(events.slice(0, 3)));
    expect(timeline.events).toHaveLength(events.length);
    expect(timeline.events[0]!.type).toBe("project.created");
    const decided = timeline.events.findIndex((e) => e.type === "gate.decided");
    expect(timeline.times[decided]! - timeline.times[decided - 1]!).toBe(MAX_GAP_MS);
    expect(countAt(timeline, -1)).toBe(0);
    expect(countAt(timeline, timeline.duration)).toBe(events.length);
    expect(nextGate(timeline, 0, 1)).toBe(timeline.times[timeline.gates[0]!]);
    expect(nextGate(timeline, 0, -1)).toBeNull();
    expect(timeAtWall(timeline, T0 + 30_500)).toBe(timeline.times[6]);
  });
});

describe("ReplayEngine", () => {
  it("rebuilds store and office from an empty state, same result when seeking", () => {
    const timeline = buildTimeline(story());
    const engine = new ReplayEngine(
      timeline,
      emptyReplayState("p-1", project({ status: "completed", spent: "9" })),
    );
    const start = engine.frameAt(0);
    expect(start.project.project?.status).toBe("draft");
    expect(start.project.agents).toEqual({});

    const working = engine.frameAt(6);
    expect(working.project.agents.an?.status).toBe("working");
    expect(avatarMode(working.office.avatars.an!, timeline.times[5]!)).toBe("walking");
    expect(working.office.avatars.an!.room).toBe("meeting_room");

    const gate = engine.frameAt(8);
    expect(gate.project.gates.g1?.status).toBe("open");
    expect(gate.office.avatars.an!.blockedBy).toBe("g1");
    expect(gate.office.documents.a1?.room).toBe("meeting_room");
    expect(gate.project.budget.spent).toBeCloseTo(0.5);

    const end = engine.frameAt(timeline.events.length);
    expect(end.office.documents.a1?.room).toBe("archive");
    // Seeking back uses a checkpoint and gives the same frame as a fresh fold.
    const again = engine.frameAt(8);
    const fresh = new ReplayEngine(timeline, emptyReplayState("p-1", project())).frameAt(8);
    expect(again.project.gates).toEqual(fresh.project.gates);
    expect(again.office.avatars).toEqual(fresh.office.avatars);
  });
});

describe("clip", () => {
  it("exports the events up to the out point and reads them back", () => {
    const events = buildTimeline(story()).events;
    const clip = makeClip({ id: "p-1", name: "GymBook" }, events, 5, 9);
    expect(clip.events).toHaveLength(10);
    expect(clip.start_at).toBe(events[5]!.created_at);
    const back = parseClip(JSON.stringify(clip));
    expect(back.events.map((e) => e.id)).toEqual(clip.events.map((e) => e.id));
    expect(() => parseClip('{"kind":"other"}')).toThrow(/not a DexterHouse/);
    expect(() => parseClip(JSON.stringify({ ...clip, events: [{ id: 1 }] }))).toThrow(/malformed/);
  });
});
