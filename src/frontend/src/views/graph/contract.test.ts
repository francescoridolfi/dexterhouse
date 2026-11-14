// SPDX-License-Identifier: AGPL-3.0-or-later
// The extractor's own example output (`src/schema/tests/fixtures/artifacts/code_graph.json`,
// added by the code-graph branch) must parse with nothing dropped. Skipped until it exists.
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { codeTarget, parseCodeGraph } from "./graphModel.ts";

const FIXTURE = resolve(
  import.meta.dirname,
  "../../../../schema/tests/fixtures/artifacts/code_graph.json",
);

describe("code_graph contract", () => {
  it.skipIf(!existsSync(FIXTURE))("parses the extractor fixture without losses", () => {
    const raw = JSON.parse(readFileSync(FIXTURE, "utf8")) as {
      nodes: unknown[];
      edges: unknown[];
    };
    const graph = parseCodeGraph(raw)!;
    expect(graph.nodes).toHaveLength(raw.nodes.length);
    expect(graph.edges).toHaveLength(raw.edges.length);
    const symbols = graph.nodes.filter((n) => n.kind === "symbol");
    expect(symbols.every((n) => codeTarget(n)?.line)).toBe(true);
  });
});
