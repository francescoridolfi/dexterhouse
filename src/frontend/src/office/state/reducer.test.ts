// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import type { EventEnvelope } from "../../api/types.ts";
import { type ProjectState, applyEvent, emptyState } from "../../store/index.ts";
import { roomAt } from "../rooms/grid.ts";
import { type OfficeModel, emptyOffice } from "./model.ts";
import { avatarMode, toolIcon } from "./mode.ts";
import { arrive, reconcile, reduceOffice } from "./reducer.ts";

let seq = 0;
function ev(type: string, payload: Record<string, unknown> = {}): EventEnvelope {
  seq += 1;
  return {
    id: `e-${seq}`,
    type,
    schema_version: 1,
    organization_id: "o",
    project_id: "p-1",
    actor: { type: "system", id: null, name: "system" },
    correlation_id: "c",
    created_at: new Date(Date.UTC(2026, 10, 1, 10, 0, seq)).toISOString(),
    payload,
  };
}

class Office {
  state: ProjectState = emptyState("p-1");
  model: OfficeModel = emptyOffice();
  now = 0;
  send(type: string, payload: Record<string, unknown> = {}) {
    const event = ev(type, payload);
    this.state = applyEvent(this.state, event);
    this.model = reduceOffice(this.model, event, this.state, this.now);
    return this;
  }
  arrive(id: string) {
    this.model = arrive(this.model, id);
    return this;
  }
  mode(id: string) {
    const avatar = this.model.avatars[id];
    return avatar ? avatarMode(avatar, this.now) : "gone";
  }
  get(id: string) {
    return this.model.avatars[id]!;
  }
}

const hire = (office: Office, id: string, role = "analyst", extra = {}) =>
  office.send("agent.hired", {
    agent_id: id,
    role,
    display_name: role,
    room: "meeting_room",
    ...extra,
  });

describe("avatar states", () => {
  it("idle in the break room after hire, walking on agent.moved, working when seated", () => {
    const o = new Office();
    hire(o, "a1");
    expect(o.mode("a1")).toBe("idle");
    expect(roomAt(o.get("a1").cell)).toBe("break_room");
    o.send("agent.moved", { agent_id: "a1", from_room: "break_room", to_room: "meeting_room" });
    expect(o.mode("a1")).toBe("walking");
    expect(o.get("a1").room).toBe("meeting_room");
    o.send("agent.turn.started", {
      agent_id: "a1",
      turn_id: "t1",
      room: "meeting_room",
      purpose: "brief",
    });
    expect(o.get("a1").hurry).toBe(true);
    o.arrive("a1");
    expect(o.mode("a1")).toBe("working");
    expect(o.get("a1").seat).not.toBeNull();
    o.send("agent.turn.completed", {
      agent_id: "a1",
      turn_id: "t1",
      cost: "0.1",
      artifacts: [{ id: "d1", kind: "analysis", version: 1 }],
    });
    expect(o.mode("a1")).toBe("idle");
    expect(o.get("a1").summary).toBe("brief");
    expect(o.model.documents.d1?.room).toBe("meeting_room");
  });

  it("walks from the HR office to the break room after a marketplace hire", () => {
    const o = new Office();
    hire(o, "m1", "designer", { source: "marketplace", room: "hr_office" });
    const avatar = o.get("m1");
    expect(roomAt(avatar.origin)).toBe("hr_office");
    expect(avatar.room).toBe("break_room");
    expect(o.mode("m1")).toBe("walking");
    o.arrive("m1");
    expect(o.mode("m1")).toBe("idle");
  });

  it("shows tools, failures and alarms for a while", () => {
    const o = new Office();
    hire(o, "a1");
    o.send("agent.turn.started", { agent_id: "a1", turn_id: "t1", room: "break_room" });
    o.send("agent.tool.used", { turn_id: "t1", tool: "fs.read_file" });
    expect(o.get("a1").tool).toBe("read");
    expect(o.get("a1").toolUntil).toBe(1_500);
    o.send("security.violation", { agent_id: "a1", turn_id: "t1", kind: "network_blocked" });
    expect(o.get("a1").alarmUntil).toBeGreaterThan(0);
    o.send("agent.turn.failed", { agent_id: "a1", turn_id: "t1", error_code: "timeout" });
    expect(o.mode("a1")).toBe("failed");
    o.now = 3_001;
    expect(o.mode("a1")).toBe("idle");
  });

  it("is blocked by an open gate of its phase until the decision", () => {
    const o = new Office();
    hire(o, "a1");
    o.send("phase.started", { phase_id: "analysis", room: "meeting_room", agents: ["a1"] });
    o.send("gate.opened", { gate_id: "g1", type: "approval", phase_id: "analysis", title: "ok?" });
    expect(o.mode("a1")).toBe("blocked");
    expect(o.model.bellRingUntil).toBeGreaterThan(0);
    o.send("gate.decided", { gate_id: "g1", decision: "approve" });
    expect(o.mode("a1")).toBe("idle");
    o.send("security.turn_blocked", { agent_id: "a1", turn_id: "t9", violations: 3 });
    expect(o.mode("a1")).toBe("blocked");
    o.send("gate.opened", { gate_id: "g2", type: "escalation", phase_id: "x" });
    o.send("gate.decided", { gate_id: "g2", decision: "retry" });
    expect(o.mode("a1")).toBe("idle");
  });

  it("hands the document off to the next room and walks back", () => {
    const o = new Office();
    hire(o, "dev", "developer");
    o.send("agent.moved", { agent_id: "dev", to_room: "open_space" }).arrive("dev");
    o.send("task.step.completed", {
      task_id: "t",
      step: "developer",
      agent_id: "dev",
      artifact: { id: "n1", kind: "dev_notes", version: 1 },
    });
    expect(o.mode("dev")).toBe("handoff");
    expect(o.get("dev").errand?.room).toBe("review_corner");
    o.arrive("dev");
    expect(o.mode("dev")).toBe("walking");
    expect(o.get("dev").errand).toBeNull();
    o.arrive("dev");
    expect(o.mode("dev")).toBe("idle");
  });

  it("celebrates at the release dock and leaves on release", () => {
    const o = new Office();
    hire(o, "pm", "project_manager");
    o.send("agent.moved", { agent_id: "pm", to_room: "release_dock" }).arrive("pm");
    o.send("release.delivered", { mode: "pull_request", pr_url: "https://x/pr/1" });
    expect(o.mode("pm")).toBe("celebrate");
    expect(o.model.dock.state).toBe("delivered");
    expect(o.model.confettiUntil).toBeGreaterThan(0);
    o.send("agent.released", { agent_id: "pm", reason: "done" });
    expect(o.mode("pm")).toBe("leaving");
    o.arrive("pm");
    expect(o.mode("pm")).toBe("gone");
  });

  it("sends unknown rooms to the open space", () => {
    const o = new Office();
    hire(o, "a1");
    o.send("agent.moved", { agent_id: "a1", to_room: "rooftop" });
    expect(o.get("a1").room).toBe("open_space");
  });

  it("gives every agent in a full room its own cell", () => {
    const o = new Office();
    for (let i = 0; i < 4; i++) hire(o, `a${i}`);
    for (let i = 0; i < 4; i++) o.send("agent.moved", { agent_id: `a${i}`, to_room: "hr_office" });
    const cells = new Set(Object.values(o.model.avatars).map((a) => `${a.cell.x},${a.cell.y}`));
    expect(cells.size).toBe(4);
    expect(Object.values(o.model.avatars).filter((a) => a.seat === null)).toHaveLength(2);
  });
});

describe("objects", () => {
  it("follow workspace, tests, packages, release and the project folder", () => {
    const o = new Office();
    o.send("workspace.created", { workspace_id: "w" });
    expect(o.model.pcs).toBe("on");
    o.send("workspace.idle");
    expect(o.model.pcs).toBe("standby");
    o.send("test.run.started", { scope: "task" });
    expect(o.model.testLight.state).toBe("running");
    o.send("test.run.completed", {
      scope: "task",
      passed: 3,
      failed: 1,
      ok: false,
      report_artifact: { id: "r1", version: 1 },
    });
    expect(o.model.testLight).toEqual({ state: "fail", detail: "3/4", reportId: "r1" });
    o.send("package.installing", { name: "designer" });
    expect(o.model.packageBox).toEqual({ state: "arriving", name: "designer" });
    o.send("package.installed", { name: "designer" });
    expect(o.model.packageBox?.state).toBe("installed");
    o.send("release.failed", { mode: "push_main", error_code: "auth" });
    expect(o.model.dock).toEqual({ state: "failed", detail: "auth" });
    o.send("project.completed");
    expect(o.model.folder).toBe("archive");
  });

  it("moves the documents of a phase to the archive when it completes", () => {
    const o = new Office();
    o.send("process.started", { phases: [{ id: "analysis", needs: [], room: "meeting_room" }] });
    o.send("phase.step.completed", {
      phase_id: "analysis",
      artifacts: [{ id: "d1", kind: "analysis", version: 1 }],
    });
    expect(o.model.documents.d1?.room).toBe("meeting_room");
    o.send("phase.completed", { phase_id: "analysis" });
    expect(o.model.documents.d1?.room).toBe("archive");
  });
});

describe("reconcile and tools", () => {
  it("adds the store's agents and releases the gone ones", () => {
    const o = new Office();
    hire(o, "a1");
    o.model = { ...o.model, avatars: {} };
    o.state = {
      ...o.state,
      agents: {
        ...o.state.agents,
        a1: { ...o.state.agents.a1!, status: "working", room: "meeting_room" },
      },
    };
    o.model = reconcile(o.model, o.state, 0);
    expect(o.get("a1").room).toBe("meeting_room");
    expect(o.mode("a1")).toBe("working");
    o.state = { ...o.state, agents: { a1: { ...o.state.agents.a1!, status: "released" } } };
    o.model = reconcile(o.model, o.state, 0);
    expect(o.mode("a1")).toBe("leaving");
  });

  it("maps tool names to icons", () => {
    expect(toolIcon("fs.write_file")).toBe("write");
    expect(toolIcon("workspace.exec")).toBe("exec");
    expect(toolIcon("tests.run")).toBe("tests");
    expect(toolIcon("marketplace.search")).toBe("marketplace");
    expect(toolIcon("memory.search")).toBe("read");
    expect(toolIcon("mystery")).toBe("other");
  });
});
