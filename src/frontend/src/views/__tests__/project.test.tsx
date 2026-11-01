// SPDX-License-Identifier: AGPL-3.0-or-later
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useProjectStore } from "../../store/projectStore.ts";
import { event, gate, snapshot, task } from "../../test/fixtures.ts";
import { json, mockApi, renderWith } from "../../test/render.tsx";
import { GatePanel } from "../gates/GatePanel.tsx";
import { ProjectPage } from "../project/ProjectPage.tsx";

const ADMIN = {
  id: "u",
  username: "ada",
  email: "",
  display_name: "Ada",
  organizations: [{ slug: "default", name: "Default", role: "admin" }],
};
const PAGE = { results: [], next: null, previous: null };

class SilentSocket {
  static OPEN = 1;
  static last: SilentSocket | null = null;
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  constructor() {
    SilentSocket.last = this;
  }
  send() {}
  close() {}
  push(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", SilentSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
  useProjectStore.getState().reset(null);
});

function renderProject(route = "/projects/p-1") {
  return renderWith(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectPage />} />
      <Route path="/projects/:projectId/:tab" element={<ProjectPage />} />
    </Routes>,
    { route },
  );
}

describe("project page", () => {
  it("keeps mode, status and budget in the header and shows the open gate first", async () => {
    mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/projects/p-1/snapshot": snapshot({
        gates_open: [
          gate({
            type: "escalation",
            payload: { title: "T-05 blocked", summary: "", artifacts: [] },
          }),
        ],
      }),
      "GET /api/v1/projects/p-1/events": PAGE,
    });
    renderProject();
    expect(await screen.findByRole("heading", { name: "GymBook" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /SUPERVISED mode/ })).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Budget used" })).toHaveAttribute(
      "aria-valuenow",
      "1",
    );
    expect(screen.getByText(/Escalation — T-05 blocked/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    // Live events update the views.
    act(() => {
      SilentSocket.last?.push({
        type: "event",
        event: event(
          "agent.turn.started",
          { turn_id: "t", agent_id: "a-2", room: "open_space", purpose: "T-01 developer" },
          { project_id: "p-1" },
        ),
      });
      SilentSocket.last?.push({
        type: "speaking",
        agent_id: "a-2",
        turn_id: "t",
        text: "Writing the booking model",
        seq: 1,
      });
    });
    expect(await screen.findByText("started: T-01 developer")).toBeInTheDocument();
    expect(screen.getByText(/Writing the booking model/)).toBeInTheDocument();
    expect(screen.getAllByText("working")).toHaveLength(2);
  });

  it("renders the board from the store and a 404 page", async () => {
    mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/projects/p-1/snapshot": snapshot({
        tasks: [task(), task({ id: "t-2", external_id: "T-02", status: "done", order: 1 })],
      }),
      "GET /api/v1/projects/p-1/events": PAGE,
      "GET /api/v1/projects/p-1/costs": {
        by_task: [{ task_id: "t-2", external_id: "T-02", cost: "1.10" }],
      },
    });
    renderProject("/projects/p-1/board");
    const done = await screen.findByRole("region", { name: /Done/ });
    expect(await within(done).findByText("€1.10")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: /Backlog/ })).getByText("Bookings"),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
    vi.stubGlobal("WebSocket", SilentSocket);
    mockApi({
      "GET /api/v1/projects/p-2/snapshot": () => json({ title: "Not found", status: 404 }, 404),
    });
    renderProject("/projects/p-2");
    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
  });
});

describe("office tab", () => {
  it("falls back to the 2D team view without WebGL 2 and keeps the scene description", async () => {
    mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/projects/p-1/snapshot": snapshot(),
      "GET /api/v1/projects/p-1/events": PAGE,
    });
    renderProject("/projects/p-1/office");
    expect(await screen.findByText(/no WebGL 2/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /agents/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try the 3D again" })).toBeInTheDocument();
    expect(screen.getByRole("tabpanel")).toHaveAttribute("id", "project-panel-office");
  });

  it("links every Log row to the replay at its time", async () => {
    mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/projects/p-1/snapshot": snapshot(),
      "GET /api/v1/projects/p-1/events": {
        ...PAGE,
        results: [event("phase.started", { phase_id: "analysis", room: "meeting_room" })],
      },
    });
    renderProject("/projects/p-1/log");
    const link = await screen.findByRole("link", { name: "Replay in the 3D office" });
    expect(link.getAttribute("href")).toMatch(/^\/projects\/p-1\/office\?replay=2026/);
  });
});

describe("gate panel", () => {
  it("requires a comment to reject and reports a decision taken by someone else", async () => {
    const { calls } = mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/gates/g-1": gate({
        artifacts: [
          {
            id: "art",
            project: "p-1",
            kind: "requirements",
            name: "requirements.md",
            version: 1,
            content_hash: "",
            phase_run: null,
            produced_by: { role: "analyst", turn_id: null },
            created_at: "2026-11-01T10:00:00Z",
            content: "# Requirements",
          },
        ],
      }),
      "POST /api/v1/gates/g-1/decide": (body) =>
        (body as { decision: string }).decision === "reject"
          ? json(
              {
                title: "Invalid transition",
                status: 409,
                detail: "Gate already decided by marta at 10:12",
              },
              409,
            )
          : json({ ...gate(), status: "approved", next: "phase_completed" }),
    });
    renderWith(<GatePanel gateId="g-1" onClose={() => undefined} />);
    const user = userEvent.setup();
    expect(await screen.findByText("# Requirements")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reject" }));
    const send = screen.getAllByRole("button", { name: "Reject" }).at(-1)!;
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText("Why (required)"), "Missing waitlist");
    await user.click(send);
    expect(await screen.findByText("Gate already decided by marta at 10:12")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText(/moves to the next phase/)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST").map((c) => c.body)).toEqual([
      { decision: "reject", comment: "Missing waitlist" },
      { decision: "approve" },
    ]);
  });

  it("enables answers only when every question has one", async () => {
    const { calls } = mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/gates/g-q": gate({
        id: "g-q",
        type: "question",
        payload: {
          title: "2 questions",
          summary: "",
          artifacts: [],
          questions: [
            { id: "q1", text: "Payments?", kind: "text", default_assumption: "No payments in 1.0" },
            { id: "q2", text: "Language?", kind: "choice", options: ["English", "Italian"] },
          ],
        },
      }),
      "POST /api/v1/gates/g-q/decide": () => json({ ...gate(), next: "phase_resumed" }),
    });
    renderWith(<GatePanel gateId="g-q" onClose={() => undefined} />);
    const user = userEvent.setup();
    const submit = await screen.findByRole("button", { name: "Send answers" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Use the assumption" }));
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: "Other" }));
    await user.type(screen.getByRole("textbox", { name: "Other" }), "German");
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        answers: [
          { question_id: "q1", answer: "No payments in 1.0" },
          { question_id: "q2", answer: "German" },
        ],
      }),
    );
    expect(await screen.findByText(/the agent resumes/)).toBeInTheDocument();
  });

  it("asks to raise the budget on the budget escalation", async () => {
    mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/gates/g-b": gate({
        id: "g-b",
        type: "escalation",
        gate_id: "budget",
        payload: { title: "Budget exhausted", summary: "", artifacts: [], reason: "budget" },
      }),
      "POST /api/v1/gates/g-b/decide": () =>
        json({ title: "Budget exceeded", status: 402, detail: "raise the budget" }, 402),
    });
    renderWith(<GatePanel gateId="g-b" onClose={() => undefined} />);
    const user = userEvent.setup();
    expect(await screen.findByText(/Raise the budget, then resume/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Resume" }));
    expect(await screen.findByText("Raise the budget first.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept as is" })).not.toBeInTheDocument();
  });
});
