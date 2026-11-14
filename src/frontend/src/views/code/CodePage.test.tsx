// SPDX-License-Identifier: AGPL-3.0-or-later
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PROJECT_ID, codeFile, codeLocation, codeTree } from "../../test/codeFixtures.ts";
import { json, mockApi, renderWith } from "../../test/render.tsx";
import { CodePage } from "./CodePage.tsx";

const BASE = `/api/v1/projects/${PROJECT_ID}`;
const PAGE = { results: [], next: null, previous: null };

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.pathname + location.search}</output>;
}

function mount(route: string, extra: Record<string, unknown> = {}) {
  const api = mockApi({
    [`GET ${BASE}`]: { id: PROJECT_ID, name: "GymBook" },
    [`GET ${BASE}/artifacts`]: PAGE,
    [`GET ${BASE}/code/tree`]: codeTree,
    [`GET ${BASE}/code/file`]: codeFile("src/gymbook/booking.py"),
    [`GET ${BASE}/code/location`]: codeLocation,
    ...extra,
  });
  renderWith(
    <Routes>
      <Route
        path="/code/:projectId"
        element={
          <>
            <CodePage />
            <Where />
          </>
        }
      />
    </Routes>,
    { route },
  );
  return api;
}

afterEach(() => vi.unstubAllGlobals());

describe("Code app", () => {
  it("opens the deep-linked file and marks the line", async () => {
    const { calls } = mount(`/code/${PROJECT_ID}?path=src/gymbook/booking.py&line=14`);
    const line = await waitFor(() => {
      const el = document.querySelector("[data-line='14']");
      expect(el).not.toBeNull();
      return el!;
    });
    expect(line).toHaveAttribute("data-highlighted", "true");
    expect(line).toHaveTextContent("def book(member: Member, slot: Slot) -> Booking:");
    expect(document.querySelectorAll("[data-highlighted]")).toHaveLength(1);
    expect(calls.some((c) => c.path.includes("/code/file?path=src%2Fgymbook%2Fbooking.py"))).toBe(
      true,
    );
    const tree = screen.getByRole("tree", { name: "Files" });
    expect(within(tree).getByRole("treeitem", { selected: true })).toHaveTextContent("booking.py");
    expect(await screen.findByText("main @ 3f9c2a7b")).toBeInTheDocument();
  });

  it("clicking a line number updates the deep link", async () => {
    mount(`/code/${PROJECT_ID}?path=src/gymbook/booking.py`);
    const gutter = await waitFor(() => {
      const el = document.querySelector("[data-line='22'] > span");
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    await userEvent.click(gutter);
    expect(screen.getByTestId("where")).toHaveTextContent(
      `/code/${PROJECT_ID}?path=src%2Fgymbook%2Fbooking.py&line=22`,
    );
  });

  it("searches files by name and opens one", async () => {
    mount(`/code/${PROJECT_ID}`);
    await screen.findByRole("tree", { name: "Files" });
    expect(screen.getByText("Pick a file on the left.")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search files by name" }), "model");
    await userEvent.click(
      within(screen.getByRole("list", { name: "Matching files" })).getByRole("button"),
    );
    expect(screen.getByTestId("where")).toHaveTextContent("path=src%2Fgymbook%2Fmodels.py");
  });

  it("shows where the code is: release, pull request and clone command", async () => {
    mount(`/code/${PROJECT_ID}`);
    const pr = await screen.findAllByRole("link", { name: /Open pull request/ });
    expect(pr[0]).toHaveAttribute("href", "https://github.com/acme/gymbook/pull/1");
    expect(screen.getAllByText(/git checkout dexterhouse\/release-1/)[0]).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Commit 3f9c2a7b/ })[0]).toHaveAttribute(
      "href",
      `https://github.com/acme/gymbook/commit/${codeTree.commit}`,
    );
  });

  it("explains a stopped workspace instead of failing", async () => {
    mount(`/code/${PROJECT_ID}`, {
      [`GET ${BASE}/code/tree`]: () =>
        json({ title: "Workspace unavailable", status: 503, detail: "no live workspace" }, 503),
    });
    expect(
      await screen.findByText("The workspace is not running, so its files cannot be read now."),
    ).toBeInTheDocument();
  });
});
