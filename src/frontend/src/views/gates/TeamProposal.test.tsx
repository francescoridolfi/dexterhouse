// SPDX-License-Identifier: AGPL-3.0-or-later
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GateTeam } from "../../api/types.ts";
import { renderWith } from "../../test/render.tsx";
import { TeamProposal } from "./TeamProposal.tsx";

const team: GateTeam = {
  artifact_id: "a1",
  marketplace_status: "reachable",
  summary: "One specialist for the UI task.",
  installed: ["htmx-frontend-developer@1.3.0"],
  proposals: [
    {
      name: "htmx-frontend-developer",
      version: "1.3.0",
      role: "htmx_frontend_developer",
      reason: "Server-rendered UI",
      for_tasks: ["T-07"],
      permissions: [{ id: "project.tasks", risk: "low" }],
      risk: "low",
      verified: true,
      rating: null,
      installs: null,
      author_github: "janedoe",
    },
  ],
};

describe("TeamProposal", () => {
  it("lists each proposal with tasks, permissions and trust", () => {
    renderWith(<TeamProposal team={team} />);
    expect(screen.getByText(/htmx-frontend-developer@1.3.0/)).toBeInTheDocument();
    expect(screen.getByText("T-07")).toBeInTheDocument();
    expect(screen.getByText("project.tasks (low)")).toBeInTheDocument();
    expect(screen.getByText(/verified · risk low · janedoe/)).toBeInTheDocument();
  });

  it("says when the marketplace was unreachable", () => {
    renderWith(
      <TeamProposal team={{ ...team, marketplace_status: "unreachable", proposals: [] }} />,
    );
    expect(screen.getByText(/marketplace was unreachable/)).toBeInTheDocument();
    expect(screen.getByText(/No specialist proposed/)).toBeInTheDocument();
  });
});
