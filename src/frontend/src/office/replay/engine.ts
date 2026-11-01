// SPDX-License-Identifier: AGPL-3.0-or-later
// Rebuilds the scene from events alone: the store's pure `applyEvent` on an empty state plus
// the office reducer, with checkpoints every 200 events for fast seeking. No state queries.
import type { EventEnvelope, Project } from "../../api/types.ts";
import { type ProjectState, emptyState } from "../../store/model.ts";
import { applyEvent } from "../../store/reducer.ts";
import { type OfficeModel, emptyOffice } from "../state/model.ts";
import { reduceOffice } from "../state/reducer.ts";
import type { Timeline } from "./timeline.ts";

const EVERY = 200;

export interface Frame {
  project: ProjectState;
  office: OfficeModel;
  /** Number of events applied. */
  count: number;
}

/** The empty store of a replay: only the project's identity, everything else from events. */
export function emptyReplayState(projectId: string, project: Project | null): ProjectState {
  const base = emptyState(projectId);
  if (!project) return base;
  return {
    ...base,
    project: { ...project, status: "draft", waiting_reason: null, spent: "0", open_gates_count: 0 },
    mode: project.execution_mode,
    budget: { ...base.budget, budget: Number(project.budget) || 0 },
    snapshotLoaded: true,
  };
}

/** The store reducer, plus the budget of `project.created` when the replay starts empty. */
export function stepProject(state: ProjectState, event: EventEnvelope): ProjectState {
  const project = applyEvent(state, event);
  const budget = Number(event.payload.budget);
  return event.type === "project.created" && project.budget.budget === 0 && budget > 0
    ? { ...project, budget: { ...project.budget, budget } }
    : project;
}

export function step(frame: Frame, event: EventEnvelope, now: number): Frame {
  const project = stepProject(frame.project, event);
  return {
    project,
    office: reduceOffice(frame.office, event, project, now),
    count: frame.count + 1,
  };
}

export class ReplayEngine {
  readonly timeline: Timeline;
  private readonly checkpoints: Frame[];

  constructor(timeline: Timeline, start: ProjectState) {
    this.timeline = timeline;
    this.checkpoints = [{ project: start, office: emptyOffice(), count: 0 }];
  }

  /** The scene after the first `count` events. */
  frameAt(count: number): Frame {
    const target = Math.max(0, Math.min(count, this.timeline.events.length));
    let index = Math.floor(target / EVERY);
    while (!this.checkpoints[index]) index -= 1;
    let frame = this.checkpoints[index]!;
    while (frame.count < target) {
      frame = this.advance(frame);
      if (frame.count % EVERY === 0 && !this.checkpoints[frame.count / EVERY]) {
        this.checkpoints[frame.count / EVERY] = frame;
      }
    }
    return frame;
  }

  advance(frame: Frame): Frame {
    const event = this.timeline.events[frame.count];
    return event ? step(frame, event, this.timeline.times[frame.count]!) : frame;
  }
}
