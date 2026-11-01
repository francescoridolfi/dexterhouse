// SPDX-License-Identifier: AGPL-3.0-or-later
/// <reference types="node" />
import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";

import en from "../i18n/en.ts";
import i18n, { pseudo } from "../i18n/index.ts";
import it_ from "../i18n/it.ts";
import { event, project } from "../test/fixtures.ts";
import tokens from "../theme/tokens.json";
import { agentColor, colorFor, roomColor } from "../theme/tokens.ts";
import { can, roleOf } from "./auth.ts";
import { actorLabel, describeEvent } from "./events.ts";
import { duration, eur, relative } from "./format.ts";
import { filterEvents } from "./logFilter.ts";
import { sortProjects } from "./projects.ts";

const t = i18n.t.bind(i18n) as TFunction;

function keys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k));
}

describe("i18n", () => {
  it("has the same keys in English and Italian", () => {
    expect(keys(it_).sort()).toEqual(keys(en).sort());
  });

  it("pseudo-localises", () => {
    expect(pseudo("Save")).toBe("⟦Sávé⟧");
  });
});

describe("theme", () => {
  it("index.css defines every colour token of tokens.json for both schemes", async () => {
    const { readFileSync } = await import("node:fs");
    const css = readFileSync(`${process.cwd()}/src/index.css`, "utf8").toLowerCase();
    const [light, dark] = css.split(":root.dark");
    for (const [name, value] of Object.entries(tokens.color)) {
      expect(light).toContain(`--dh-${name}: ${value.light.toLowerCase()};`);
      expect(dark).toContain(`--dh-${name}: ${value.dark.toLowerCase()};`);
    }
  });

  it("resolves agent and room colours", () => {
    expect(agentColor("analyst")).toBe("#7DB7E7");
    expect(agentColor("x", "#abcdef")).toBe("#abcdef");
    expect(agentColor("custom-role", "nope")).toMatch(/^#/);
    expect(roomColor("qa_lab")).toBe("#E77DA6");
    expect(roomColor("unknown")).toBe("#C9C9C9");
    expect(colorFor("dark", "accent")).toBe("#5B8DEF");
  });
});

describe("formatting and events", () => {
  it("formats money, durations and relative times", () => {
    expect(eur("16.2")).toBe("€16.20");
    expect(eur("0.000781")).toBe("€0.0008");
    expect(duration(42)).toBe("42 s");
    expect(duration(4320)).toBe("1 h 12 min");
    expect(duration(null)).toBe("");
    expect(relative(new Date(Date.now() - 120_000).toISOString())).toBe("2 minutes ago");
  });

  it("describes events and their actors", () => {
    const tool = event("agent.tool.used", {
      tool: "workspace.exec",
      duration_ms: 6400,
      allowed: true,
    });
    expect(describeEvent(tool, t)).toMatchObject({
      text: "workspace.exec (6400 ms)",
      tone: "tool",
    });
    const iteration = event("task.iteration", {
      task_id: "t",
      iteration: 3,
      max_iterations: 3,
      reason: "tests",
    });
    expect(describeEvent(iteration, t, { t: { external_id: "T-05" } }).text).toBe(
      "T-05 → 3/3 (tests)",
    );
    expect(describeEvent(event("custom.thing"), t).text).toBe("custom.thing");
    const agentEvent = event("agent.turn.started", { agent_id: "a-1", purpose: "x" });
    expect(actorLabel(agentEvent, { "a-1": { displayName: "Analyst" } }, t)).toBe("Analyst");
    expect(actorLabel(event("project.started"), {}, t)).toBe("system");
  });

  it("filters the timeline by family, agent, phase and text", () => {
    const rows = [
      event("phase.started", { phase_id: "analysis" }),
      event("agent.tool.used", { agent_id: "a-1", tool: "memory.search" }),
      event("gate.opened", { title: "Approve architecture", phase_id: "architecture" }),
    ];
    const run = (f: Partial<Parameters<typeof filterEvents>[1]>) =>
      filterEvents(rows, { family: "", agent: "", phase: "", text: "", ...f }, (e) => e.type).map(
        (e) => e.type,
      );
    expect(run({ family: "agent" })).toEqual(["agent.tool.used"]);
    expect(run({ agent: "a-1" })).toEqual(["agent.tool.used"]);
    expect(run({ phase: "architecture" })).toEqual(["gate.opened"]);
    expect(run({ text: "ARCHITECTURE" })).toEqual(["gate.opened"]);
  });
});

describe("projects and roles", () => {
  it("lists projects with open gates first, then by update", () => {
    const sorted = sortProjects([
      project({ id: "a", updated_at: "2026-11-02T00:00:00Z" }),
      project({ id: "b", open_gates_count: 1, updated_at: "2026-10-01T00:00:00Z" }),
      project({ id: "c", updated_at: "2026-11-03T00:00:00Z" }),
    ]);
    expect(sorted.map((p) => p.id)).toEqual(["b", "c", "a"]);
  });

  it("ranks roles", () => {
    const user = {
      id: "u",
      username: "u",
      email: "",
      display_name: "u",
      organizations: [{ slug: "d", name: "D", role: "admin" as const }],
    };
    expect(roleOf(user)).toBe("admin");
    expect(can(user, "member")).toBe(true);
    expect(can(user, "owner")).toBe(false);
    expect(can(undefined, "member")).toBe(false);
  });
});
