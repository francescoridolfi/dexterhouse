// SPDX-License-Identifier: AGPL-3.0-or-later
// Contract with the extractor (PR #30): its example output
// `src/schema/tests/fixtures/artifacts/code_graph.json` must parse with nothing dropped and
// render in the artifact viewer like any `code_graph` artifact.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { graphArtifact } from "../../test/codeFixtures.ts";
import { mockApi, renderWith } from "../../test/render.tsx";
import { ArtifactViewer } from "../project/panels/ArtifactViewer.tsx";
import { codeTarget, parseCodeGraph } from "./graphModel.ts";

const FIXTURE = resolve(
  import.meta.dirname,
  "../../../../schema/tests/fixtures/artifacts/code_graph.json",
);

interface Raw {
  commit: string;
  nodes: { id: string; kind: string; label: string; path: string | null; line: number | null }[];
  edges: { kind: string }[];
}

const raw = JSON.parse(readFileSync(FIXTURE, "utf8")) as Raw;

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.pathname + location.search}</output>;
}

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("code_graph contract (extractor fixture)", () => {
  it("parses without losses; every symbol opens in Code at its line", () => {
    const graph = parseCodeGraph(raw)!;
    expect(graph.nodes).toHaveLength(raw.nodes.length);
    expect(graph.edges).toHaveLength(raw.edges.length);
    expect(graph.commit).toBe(raw.commit);
    const symbols = graph.nodes.filter((n) => n.kind === "symbol");
    expect(symbols.length).toBeGreaterThan(0);
    expect(symbols.every((n) => codeTarget(n)?.line)).toBe(true);
  });

  it("renders in the artifact viewer and opens a symbol in Code", async () => {
    const artifact = graphArtifact({ data: raw });
    mockApi({
      [`GET /api/v1/artifacts/${artifact.id}`]: artifact,
      [`GET /api/v1/artifacts/${artifact.id}/versions`]: { results: [artifact] },
    });
    renderWith(
      <Routes>
        <Route path="/" element={<ArtifactViewer artifactId={artifact.id} />} />
        <Route path="*" element={<Where />} />
      </Routes>,
    );
    const label = `Dependency graph with ${raw.nodes.length} nodes and ${raw.edges.length} edges`;
    expect(await screen.findByRole("img", { name: label })).toBeInTheDocument();
    for (const kind of ["imports", "defines", "calls", "inherits", "tests"]) {
      const count = raw.edges.filter((e) => e.kind === kind).length;
      const edges = screen.getByRole("group", { name: "Edge kinds" });
      expect(
        within(edges).getByRole("button", { name: new RegExp(`^${kind}\\s*${count}$`) }),
      ).toBeInTheDocument();
    }
    const method = raw.nodes.find((n) => n.kind === "symbol" && n.label.includes("."))!;
    await userEvent.type(screen.getByRole("searchbox", { name: "Search nodes" }), method.label);
    const results = screen.getByRole("list", { name: "Matching nodes" });
    await userEvent.click(within(results).getByRole("button", { name: method.label }));
    await userEvent.click(screen.getByRole("button", { name: "Open in Code" }));
    const where = new URL(screen.getByTestId("where").textContent, "http://x");
    expect(where.pathname).toBe(`/code/${artifact.project}`);
    expect(where.searchParams.get("path")).toBe(method.path);
    expect(where.searchParams.get("line")).toBe(String(method.line));
    expect(where.searchParams.get("ref")).toBe(raw.commit);
  });
});
