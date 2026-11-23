// SPDX-License-Identifier: AGPL-3.0-or-later
import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";

import i18n from "../i18n/index.ts";
import { event, project, snapshot } from "../test/fixtures.ts";
import { describeEvent } from "../utils/events.ts";
import { emptyState } from "./model.ts";
import { applyEvent, applySnapshot } from "./reducer.ts";

const t = i18n.t.bind(i18n) as TFunction;
const completed = () =>
  applySnapshot(emptyState(), snapshot({ project: project({ status: "completed" }) }));

describe("E-13 events in the store", () => {
  it("keeps context.* and change_request.* events for the log", () => {
    const state = [
      event("context.added", { artifact: { id: "d", kind: "context", version: 1 }, size: 1 }),
      event("change_request.created", { change_request: { number: 1, title: "x" } }),
    ].reduce(applyEvent, completed());
    expect(state.events.map((e) => e.type)).toEqual(["context.added", "change_request.created"]);
    expect(state.unknownEvents).toBe(0);
  });

  it("project.reopened puts a completed project back to running with fresh phases", () => {
    const state = applyEvent(
      completed(),
      event("project.reopened", { change_request: "cr-1", iteration: 1 }),
    );
    expect(state.project?.status).toBe("running");
    expect(state.phases.analysis).toMatchObject({ status: "pending", runId: null, agents: [] });
    expect(state.phaseOrder).toEqual(["analysis", "implementation"]);
  });
});

describe("E-13 log lines", () => {
  it("describes context documents", () => {
    expect(describeEvent(event("context.added", { filename: "analysis.pdf" }), t).text).toBe(
      "context document added: analysis.pdf",
    );
    expect(describeEvent(event("context.processed", { chars: 4200 }), t)).toMatchObject({
      tone: "ok",
      text: "context document ready (4200 characters)",
    });
    expect(describeEvent(event("context.failed", { reason: "no_text_layer" }), t)).toMatchObject({
      tone: "error",
      text: expect.stringContaining("no OCR") as string,
    });
    expect(describeEvent(event("context.deactivated", {}), t).text).toBe(
      "context document deactivated",
    );
  });

  it("describes change requests and the reopening", () => {
    expect(
      describeEvent(
        event("change_request.created", { change_request: { number: 2, title: "Dark mode" } }),
        t,
      ).text,
    ).toBe("CR-2 created: Dark mode");
    expect(describeEvent(event("change_request.failed", { number: 2 }), t)).toMatchObject({
      tone: "error",
      text: "CR-2 failed",
    });
    expect(
      describeEvent(event("project.reopened", { change_request: { number: 1 }, iteration: 1 }), t)
        .text,
    ).toBe("project reopened for CR-1 (iteration 1)");
  });
});
