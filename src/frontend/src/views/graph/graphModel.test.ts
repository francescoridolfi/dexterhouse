// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { codeGraphData } from "../../test/codeFixtures.ts";
import { ForceLayout } from "./forceLayout.ts";
import {
  codeTarget,
  communityColor,
  filterGraph,
  kindsOf,
  neighbors,
  NODE_KINDS,
  parseCodeGraph,
  searchNodes,
} from "./graphModel.ts";

describe("code graph model", () => {
  it("parses the schema-1 contract", () => {
    const graph = parseCodeGraph(codeGraphData)!;
    expect(graph.nodes).toHaveLength(14);
    expect(graph.edges).toHaveLength(17);
    expect(graph.commit).toBe(codeGraphData.commit);
  });

  it("keeps what is well formed and never throws on agent output", () => {
    expect(parseCodeGraph(null)).toBeNull();
    expect(parseCodeGraph({ nodes: [] })).toBeNull();
    expect(parseCodeGraph({ schema: 2, nodes: [], edges: [] })).toBeNull();
    const graph = parseCodeGraph({
      nodes: [{ id: "a", kind: "widget", line: -4 }, { id: "a" }, { label: "no id" }, 7, { id: 2 }],
      edges: [
        { source: "a", target: "2", kind: "calls" },
        { source: "a", target: "2", kind: "calls" },
        { source: "a", target: "ghost" },
        "junk",
      ],
    })!;
    expect(graph.nodes.map((n) => n.id)).toEqual(["a", "2"]);
    expect(graph.nodes[0]).toMatchObject({ kind: "widget", label: "a", line: null });
    expect(graph.edges).toEqual([{ source: "a", target: "2", kind: "calls" }]);
    expect(kindsOf(["widget", "file"], NODE_KINDS)).toEqual(["file", "widget"]);
  });

  it("filters, searches and lists neighbours", () => {
    const graph = parseCodeGraph(codeGraphData)!;
    const files = filterGraph(graph, new Set(["file"]), new Set(["imports"]));
    expect(files.nodes.every((n) => n.kind === "file")).toBe(true);
    expect(files.edges).toHaveLength(3);
    expect(searchNodes(graph.nodes, "book").map((n) => n.label)).toEqual([
      "book",
      "Booking",
      "booking.py",
      "create_booking",
      "gymbook",
      "test_booking.py",
    ]);
    expect(searchNodes(graph.nodes, "gymbook/models").map((n) => n.label)).toEqual([
      "Member",
      "models.py",
      "Slot",
    ]);
    const near = neighbors(graph, "sym:src/gymbook/booking.py:book");
    expect(near.map((n) => `${n.direction}:${n.kind}:${n.node.label}`).sort()).toEqual([
      "in:calls:create_booking",
      "in:defines:booking.py",
      "in:tests:test_full_slot",
      "out:calls:Booking",
    ]);
  });

  it("opens files and symbols in Code, not modules or externals", () => {
    const graph = parseCodeGraph(codeGraphData)!;
    const byId = (id: string) => graph.nodes.find((n) => n.id === id)!;
    expect(codeTarget(byId("sym:src/gymbook/booking.py:book"))).toEqual({
      path: "src/gymbook/booking.py",
      line: 14,
    });
    expect(codeTarget(byId("file:src/gymbook/api.py"))).toEqual({
      path: "src/gymbook/api.py",
      line: null,
    });
    expect(codeTarget(byId("ext:fastapi"))).toBeNull();
    expect(codeTarget(byId("mod:gymbook"))).toBeNull();
  });

  it("gives each community a stable colour", () => {
    expect(communityColor(1)).toBe(communityColor(1));
    expect(communityColor(1)).not.toBe(communityColor(2));
    expect(communityColor(null)).toMatch(/^hsl/);
  });
});

describe("force layout", () => {
  it("settles with linked nodes closer than unlinked ones", () => {
    const ids = Array.from({ length: 40 }, (_, i) => `n${i}`);
    const links = ids.slice(1, 20).map((_, i) => ({ source: 0, target: i + 1 }));
    const layout = new ForceLayout(ids, links);
    layout.run(400);
    expect(layout.settled).toBe(true);
    const d = (a: number, b: number) =>
      Math.hypot(layout.nodes[a]!.x - layout.nodes[b]!.x, layout.nodes[a]!.y - layout.nodes[b]!.y);
    const linked = links.reduce((sum, l) => sum + d(l.source, l.target), 0) / links.length;
    const loose = ids.slice(20).reduce((sum, _, i) => sum + d(0, i + 20), 0) / 20;
    expect(linked).toBeLessThan(loose);
    for (const n of layout.nodes) expect(Number.isFinite(n.x) && Number.isFinite(n.y)).toBe(true);
  });

  it("keeps coincident nodes finite and finds the nearest node", () => {
    const layout = new ForceLayout(["a", "b"], []);
    layout.nodes.forEach((n) => Object.assign(n, { x: 0, y: 0 }));
    layout.run(50);
    expect(layout.nodes.every((n) => Number.isFinite(n.x))).toBe(true);
    expect(layout.nodes[0]!.x).not.toBe(layout.nodes[1]!.x);
    expect(layout.find(layout.nodes[1]!.x, layout.nodes[1]!.y, 0.001)).toBe(1);
    expect(layout.find(1e6, 1e6, 5)).toBe(-1);
  });
});
