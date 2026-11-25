// SPDX-License-Identifier: AGPL-3.0-or-later
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useProjectStore } from "../../../store/projectStore.ts";
import { changeRequest, page, user } from "../../../test/e13Fixtures.ts";
import { event, project, snapshot } from "../../../test/fixtures.ts";
import { json, mockApi, renderWith } from "../../../test/render.tsx";
import { ProjectHeader } from "../ProjectHeader.tsx";
import { ChangesTab } from "../tabs/ChangesTab.tsx";

const LIST = "GET /api/v1/projects/p-1/change-requests";
const CRS = [
  changeRequest(),
  changeRequest({
    id: "cr-0",
    number: 0,
    title: "Fix booking reminder",
    status: "completed",
    started_at: "2026-11-02T11:00:00Z",
    completed_at: "2026-11-02T13:00:00Z",
    cost: "4.20",
    release: { number: 2, url: "https://github.com/acme/gym/pull/7" },
  }),
];

function open(status: "completed" | "running" = "completed") {
  useProjectStore.getState().snapshot(snapshot({ project: project({ status }) }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  useProjectStore.getState().reset(null);
});

const posts = (calls: ReturnType<typeof mockApi>["calls"]) =>
  calls.filter((c) => c.method === "POST").map((c) => c.path);

describe("ChangesTab", () => {
  it("lists CRs newest first with status, budget, cost and release link", async () => {
    open();
    mockApi({ "GET /api/v1/auth/me": user("viewer"), [LIST]: page(CRS) });
    renderWith(<ChangesTab />);
    const rows = within(await screen.findByRole("list", { name: "Change requests" })).getAllByRole(
      "listitem",
    );
    expect(rows[0]).toHaveTextContent("CR-1Add waiting list");
    expect(rows[0]).toHaveTextContent("draft");
    expect(rows[0]).toHaveTextContent("budget €15 · spent €0.00");
    expect(rows[1]).toHaveTextContent("spent €4.20");
    expect(within(rows[1]!).getByRole("link", { name: /release-2/ })).toHaveAttribute(
      "href",
      "https://github.com/acme/gym/pull/7",
    );
    // Viewers see the body but no action.
    await userEvent.click(within(rows[0]!).getByRole("button", { name: /Add waiting list/ }));
    expect((await within(rows[0]!).findByText("waiting list")).tagName).toBe("STRONG");
    expect(
      screen.queryByRole("button", { name: /New change request|Edit|Start|Queue/ }),
    ).toBeNull();
  });

  it("lets an admin start a draft on a completed project and a member only estimate", async () => {
    open();
    const { calls } = mockApi({
      "GET /api/v1/auth/me": user("admin"),
      [LIST]: page(CRS),
      "POST /api/v1/change-requests/cr-1/queue": () => json(changeRequest({ status: "running" })),
      "GET /api/v1/change-requests/cr-1/estimate": { low: 6, high: 18, basis: "static" },
    });
    renderWith(<ChangesTab />);
    await userEvent.click(await screen.findByRole("button", { name: /Add waiting list/ }));
    await userEvent.click(screen.getByRole("button", { name: "Estimate" }));
    expect(await screen.findByText("estimated €6–€18")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start" }));
    const dialog = screen.getByRole("alertdialog", { name: "Start CR-1?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Start" }));
    await waitFor(() => expect(posts(calls)).toEqual(["/api/v1/change-requests/cr-1/queue"]));
  });

  it("shows Queue on a running project and no queue/cancel for members", async () => {
    open("running");
    mockApi({ "GET /api/v1/auth/me": user("admin"), [LIST]: page(CRS) });
    const view = renderWith(<ChangesTab />);
    await userEvent.click(await screen.findByRole("button", { name: /Add waiting list/ }));
    expect(screen.getByRole("button", { name: "Queue" })).toBeInTheDocument();
    view.unmount();

    mockApi({ "GET /api/v1/auth/me": user("member"), [LIST]: page(CRS) });
    renderWith(<ChangesTab />);
    await userEvent.click(await screen.findByRole("button", { name: /Add waiting list/ }));
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^(Queue|Start|Cancel CR)$/ })).toBeNull();
    // A completed CR cannot be edited.
    await userEvent.click(screen.getByRole("button", { name: /Fix booking reminder/ }));
    expect(screen.getAllByRole("button", { name: "Edit" })).toHaveLength(1);
  });

  it("creates a draft, then uploads attachments with change_request set", async () => {
    open();
    const { fetchMock, calls } = mockApi({
      "GET /api/v1/auth/me": user("member"),
      [LIST]: page([]),
      "POST /api/v1/projects/p-1/change-requests": () =>
        json(changeRequest({ id: "cr-5", number: 5 }), 201),
      "POST /api/v1/projects/p-1/context": () => json({ id: "d" }, 202),
    });
    renderWith(<ChangesTab />);
    expect(await screen.findByText("No change requests.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New change request" }));
    await userEvent.type(screen.getByLabelText("Title"), "Waiting list");
    await userEvent.type(screen.getByLabelText("What should change"), "Add a waiting list");
    const budget = screen.getByLabelText("Budget");
    await userEvent.clear(budget);
    await userEvent.type(budget, "12,5");
    const file = new File(["spec"], "waitlist.md", { type: "text/markdown" });
    await userEvent.upload(screen.getByLabelText("Choose files…"), file);
    await userEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(posts(calls)).toEqual([
        "/api/v1/projects/p-1/change-requests",
        "/api/v1/projects/p-1/context",
      ]),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      title: "Waiting list",
      body: "Add a waiting list",
      budget: "12.5",
    });
    const form = fetchMock.mock.calls[calls.findIndex((c) => c.path.endsWith("/context"))]?.[1]
      ?.body as FormData;
    expect(form.get("change_request")).toBe("cr-5");
    expect(form.get("file")).toBe(file);
  });

  it("edits a draft with PATCH", async () => {
    open();
    const { calls } = mockApi({
      "GET /api/v1/auth/me": user("member"),
      [LIST]: page([changeRequest()]),
      "PATCH /api/v1/change-requests/cr-1": () => json(changeRequest({ title: "Waitlist" })),
    });
    renderWith(<ChangesTab />);
    await userEvent.click(await screen.findByRole("button", { name: /Add waiting list/ }));
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const title = screen.getByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "Waitlist");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ title: "Waitlist" }),
    );
  });
});

describe("ProjectHeader change request badge", () => {
  it("shows the running CR next to the status and follows CR events", async () => {
    open("running");
    let status = "queued";
    mockApi({
      "GET /api/v1/auth/me": user("member"),
      [LIST]: () => json(page([changeRequest({ number: 2, status: status as "queued" })])),
    });
    renderWith(<ProjectHeader />);
    expect(await screen.findByText("CR-2 · queued")).toBeInTheDocument();
    status = "running";
    act(() => {
      useProjectStore.getState().event(event("change_request.started", { number: 2 }));
    });
    expect(await screen.findByText("CR-2 · running")).toBeInTheDocument();
  });
});
