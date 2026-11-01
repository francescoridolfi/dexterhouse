// SPDX-License-Identifier: AGPL-3.0-or-later
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "../../App.tsx";
import { BudgetBar } from "../../components/Badges.tsx";
import { project } from "../../test/fixtures.ts";
import { json, mockApi, renderWith } from "../../test/render.tsx";

const ME = {
  id: "u",
  username: "ada",
  email: "",
  display_name: "Ada",
  organizations: [{ slug: "default", name: "Default", role: "owner" }],
};
const GOOD = "right"; // the test password  pragma: allowlist secret
const EMPTY_PAGE = { results: [], next: null, previous: null };

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("authentication", () => {
  it("sends anonymous users to the login, then to the projects with CSRF", async () => {
    let logged = false;
    document.cookie = "csrftoken=abc123";
    const { calls } = mockApi({
      "GET /api/v1/auth/me": () =>
        logged ? json(ME) : json({ title: "Forbidden", status: 403 }, 403),
      "GET /api/v1/auth/csrf": { detail: "ok" },
      "POST /api/v1/auth/login": (body) => {
        const { password } = body as { password: string }; // pragma: allowlist secret
        if (password !== GOOD) return json({ title: "Invalid", status: 401, detail: "bad" }, 401);
        logged = true;
        return json(ME);
      },
      "GET /api/v1/projects": { ...EMPTY_PAGE, results: [project()] },
      "GET /api/v1/gates": EMPTY_PAGE,
    });
    renderWith(<AppRoutes />, { route: "/projects" });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Username"), "ada");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password.");
    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Password"), "right");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(await screen.findByText("GymBook")).toBeInTheDocument();
    const login = calls.find((c) => c.method === "POST");
    expect(login?.headers["X-CSRFToken"]).toBe("abc123");
  });
});

describe("projects list", () => {
  it("shows status, mode, budget and open gates; empty and error states", async () => {
    mockApi({
      "GET /api/v1/auth/me": ME,
      "GET /api/v1/gates": EMPTY_PAGE,
      "GET /api/v1/projects": {
        ...EMPTY_PAGE,
        results: [
          project({
            id: "a",
            name: "Landing",
            status: "completed",
            completed_at: "2026-11-01T00:00:00Z",
          }),
          project({
            id: "b",
            name: "Portfolio",
            execution_mode: "autonomous",
            status: "waiting",
            waiting_reason: "budget",
            open_gates_count: 1,
            spent: "20",
            budget: "20",
          }),
        ],
      },
    });
    renderWith(<AppRoutes />, { route: "/projects" });
    const rows = await screen.findAllByRole("listitem");
    const first = within(rows[0]!);
    expect(first.getByText("Portfolio")).toBeInTheDocument();
    expect(first.getByText("AUTONOMOUS")).toBeInTheDocument();
    expect(first.getByText(/budget exceeded/)).toBeInTheDocument();
    expect(first.getByLabelText("1 open gate")).toBeInTheDocument();
    expect(first.getByRole("meter")).toHaveAttribute("aria-valuenow", "20");
  });

  it("explains an empty organization and a failing core", async () => {
    mockApi({
      "GET /api/v1/auth/me": ME,
      "GET /api/v1/gates": EMPTY_PAGE,
      "GET /api/v1/projects": EMPTY_PAGE,
    });
    renderWith(<AppRoutes />, { route: "/projects" });
    expect(await screen.findByText(/No projects yet/)).toBeInTheDocument();
    vi.unstubAllGlobals();
    mockApi({
      "GET /api/v1/auth/me": ME,
      "GET /api/v1/gates": EMPTY_PAGE,
      "GET /api/v1/projects": () =>
        json({ title: "Unavailable", status: 503, detail: "core down" }, 503),
    });
    renderWith(<AppRoutes />, { route: "/projects" });
    expect(await screen.findByText("core down")).toBeInTheDocument();
  });
});

describe("new project", () => {
  it("shows inline errors from problem+json", async () => {
    mockApi({
      "GET /api/v1/auth/me": ME,
      "GET /api/v1/gates": EMPTY_PAGE,
      "GET /api/v1/meta": {
        processes: [{ name: "software-house-default", version: "1", phases: [], requirements: {} }],
        features: {},
        providers: [],
        version: "0",
        "3d_enabled": false,
      },
      "GET /api/v1/estimate": { low: 8, high: 25, basis: "static", currency: "EUR" },
      "POST /api/v1/projects": () =>
        json(
          {
            title: "Validation failed",
            status: 400,
            detail: "invalid",
            errors: [
              { field: "budget", message: "Ensure this value is greater than or equal to 0." },
            ],
          },
          400,
        ),
    });
    renderWith(<AppRoutes />, { route: "/projects/new" });
    const user = userEvent.setup();
    expect(await screen.findByText(/Similar projects: €8–€25/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Name"), "GymBook");
    await user.type(screen.getByLabelText("Brief (Markdown)"), "A gym app");
    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(
      await screen.findByText("Ensure this value is greater than or equal to 0."),
    ).toBeInTheDocument();
    expect(screen.getByText("9 / 20000 characters")).toBeInTheDocument();
  });
});

describe("BudgetBar", () => {
  it("exposes the spend as a meter and flags overspend", () => {
    renderWith(<BudgetBar spent="21" budget="20" />);
    const meter = screen.getByRole("meter", { name: "Budget used" });
    expect(meter).toHaveAttribute("aria-valuetext", "€21.00 of €20.00");
    expect(screen.getByText("€21.00 / €20")).toHaveClass("text-failed");
  });
});

describe("inbox", () => {
  it("lists escalations first", async () => {
    mockApi({
      "GET /api/v1/auth/me": ME,
      "GET /api/v1/projects": { ...EMPTY_PAGE, results: [project()] },
      "GET /api/v1/gates": {
        ...EMPTY_PAGE,
        results: [
          {
            id: "1",
            project: "p-1",
            type: "approval",
            opened_at: "2026-11-01T09:00:00Z",
            payload: { title: "Approve architecture", summary: "", artifacts: [] },
          },
          {
            id: "2",
            project: "p-1",
            type: "escalation",
            opened_at: "2026-11-01T10:00:00Z",
            payload: { title: "T-05 blocked", summary: "", artifacts: [] },
          },
        ],
      },
    });
    renderWith(<AppRoutes />, { route: "/inbox" });
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("T-05 blocked");
    expect(within(items[0]!).getByRole("button", { name: "Open" })).toBeInTheDocument();
    expect(within(items[1]!).getByRole("button", { name: "Review" })).toBeInTheDocument();
  });
});
