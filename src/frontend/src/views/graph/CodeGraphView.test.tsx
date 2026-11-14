// SPDX-License-Identifier: AGPL-3.0-or-later
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { graphArtifact } from "../../test/codeFixtures.ts";
import { mockApi, renderWith } from "../../test/render.tsx";
import { ArtifactViewer } from "../project/panels/ArtifactViewer.tsx";
import { GraphPage } from "./GraphPage.tsx";

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.pathname + location.search}</output>;
}

beforeEach(() => {
  // jsdom has no 2D canvas: the renderer must cope (and stay silent).
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function mount(artifact = graphArtifact()) {
  mockApi({
    "GET /api/v1/artifacts/a-graph": artifact,
    "GET /api/v1/artifacts/a-graph/versions": { results: [artifact] },
  });
  renderWith(
    <Routes>
      <Route path="/" element={<ArtifactViewer artifactId="a-graph" />} />
      <Route path="/graph/:artifactId" element={<GraphPage />} />
      <Route path="*" element={<Where />} />
    </Routes>,
  );
}

describe("code_graph renderer", () => {
  it("renders the graph with node and edge filters instead of raw JSON", async () => {
    mount();
    expect(
      await screen.findByRole("img", { name: /Dependency graph with 14 nodes and 17 edges/ }),
    ).toBeInTheDocument();
    const symbols = screen.getByRole("button", { name: /Symbols\s*7/ });
    expect(symbols).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(symbols);
    expect(symbols).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("img", { name: /7 nodes and 8 edges/ })).toBeInTheDocument();
    const edges = screen.getByRole("group", { name: "Edge kinds" });
    await userEvent.click(within(edges).getByRole("button", { name: /imports/ }));
    expect(screen.getByRole("img", { name: /7 nodes and 3 edges/ })).toBeInTheDocument();
  });

  it("searches, shows neighbours and opens a symbol in Code at its line", async () => {
    mount();
    await userEvent.type(await screen.findByRole("searchbox", { name: "Search nodes" }), "book");
    const results = screen.getByRole("list", { name: "Matching nodes" });
    await userEvent.click(within(results).getByRole("button", { name: "book" }));
    const panel = screen.getByRole("complementary", { name: "Selected node" });
    expect(within(panel).getByText("4 neighbours")).toBeInTheDocument();
    expect(within(panel).getByText("src/gymbook/booking.py:14")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: /create_booking/ }));
    expect(within(panel).getByText("create_booking")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Open in Code" }));
    expect(screen.getByTestId("where")).toHaveTextContent(
      "/code/p-1?path=src%2Fgymbook%2Fapi.py&line=16&ref=3f9c2a7b1d4e5f60718293a4b5c6d7e8f9012345",
    );
  });

  it("opens the full graph in its own window", async () => {
    mount();
    const link = await screen.findByRole("link", { name: "Open in window" });
    expect(link).toHaveAttribute("href", "/graph/a-graph");
    await userEvent.click(link);
    expect(await screen.findByRole("heading", { name: /code_graph.json/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /14 nodes/ })).toBeInTheDocument();
  });

  it("falls back to the raw view for an unreadable graph", async () => {
    mount(graphArtifact({ data: { nodes: "nope" } }));
    expect(await screen.findByText(/nope/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Dependency graph/ })).toBeNull();
  });
});
