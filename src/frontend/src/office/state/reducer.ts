// SPDX-License-Identifier: AGPL-3.0-or-later
// Pure office reducer: event (+ the project state after it) → avatar states and objects.
// Same function for the live scene and the replay (events alone rebuild the office).
import type { EventEnvelope } from "../../api/types.ts";
import type { ProjectState } from "../../store/model.ts";
import { resolveRoom } from "../rooms/roomFor.ts";
import { type AvatarModel, type OfficeModel, TIMERS } from "./model.ts";
import { toolIcon } from "./mode.ts";
import { IDLE, errandTo, leave, moveTo, newAvatar, put } from "./placement.ts";
import { reduceObjects } from "./objects.ts";

type Payload = Record<string, unknown>;
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

/** Hand-off destination after a task step (who takes the document next). */
function nextRoom(step: string | null, verdict: string | null): string | null {
  if (step === "developer") return "review_corner";
  if (step === "reviewer") return verdict === "request_changes" ? "open_space" : "qa_lab";
  if (step === "tester") return verdict === "fail" ? "open_space" : "pm_office";
  return null;
}

function byTurn(model: OfficeModel, turnId: string | null): AvatarModel | undefined {
  return turnId ? Object.values(model.avatars).find((a) => a.turnId === turnId) : undefined;
}

function update(
  model: OfficeModel,
  avatar: AvatarModel | undefined,
  fn: (a: AvatarModel) => AvatarModel,
): OfficeModel {
  return avatar ? put(model, fn(avatar)) : model;
}

/** Agents a gate waits on: the task's agent, else the agents of the gate's phase. */
function gateAgents(state: ProjectState, p: Payload): string[] {
  const task = state.tasks[str(p.task_id) ?? ""];
  if (task?.assigned_agent) return [task.assigned_agent];
  return state.phases[str(p.phase_id) ?? ""]?.agents ?? [];
}

function hire(model: OfficeModel, p: Payload, now: number): OfficeModel {
  const id = str(p.agent_id);
  if (!id || (model.avatars[id] && !model.avatars[id].leaving)) return model;
  const marketplace = p.source === "marketplace" || p.room === "hr_office";
  if (!marketplace) return put(model, newAvatar(model, id, IDLE, now));
  // Marketplace hire: appears at the HR desk, then walks to the break room (E-08 hand-over).
  const hired = newAvatar(model, id, "hr_office", now);
  const withHr = put(model, hired);
  return put(withHr, moveTo(withHr, hired, IDLE));
}

function reduceAvatars(
  model: OfficeModel,
  event: EventEnvelope,
  state: ProjectState,
  now: number,
): OfficeModel {
  const p = event.payload ?? {};
  const agent = model.avatars[str(p.agent_id) ?? ""];
  switch (event.type) {
    case "agent.hired":
      return hire(model, p, now);
    case "agent.released":
      return update(model, agent, leave);
    case "agent.moved":
      return agent && !agent.leaving
        ? put(model, { ...moveTo(model, agent, str(p.to_room) ?? IDLE), hurry: false })
        : model;
    case "agent.status":
      return update(model, agent, (a) =>
        p.status === "blocked"
          ? { ...a, blockedBy: a.blockedBy ?? "status" }
          : a.blockedBy === "status"
            ? { ...a, blockedBy: null }
            : a,
      );
    case "agent.turn.started":
      return update(model, agent, (a) => {
        const room = str(p.room);
        const moved = room && resolveRoom(room).id !== a.room ? moveTo(model, a, room) : a;
        const walking = moved.walking || a.walking;
        return {
          ...moved,
          errand: null,
          walking,
          hurry: walking,
          working: true,
          turnId: str(p.turn_id),
          purpose: str(p.purpose),
          failedUntil: 0,
        };
      });
    case "agent.turn.completed":
      return update(model, agent, (a) => {
        const summary = str(p.summary) ?? a.purpose;
        return {
          ...a,
          working: false,
          turnId: null,
          purpose: null,
          summary,
          summaryUntil: summary ? now + TIMERS.summary : 0,
        };
      });
    case "agent.turn.failed":
      return update(model, agent, (a) => ({
        ...a,
        working: false,
        turnId: null,
        failedUntil: now + TIMERS.failed,
      }));
    case "agent.turn.cancelled":
      return update(model, byTurn(model, str(p.turn_id)), (a) => ({
        ...a,
        working: false,
        turnId: null,
      }));
    case "agent.tool.requested":
    case "agent.tool.used":
      return update(model, byTurn(model, str(p.turn_id)), (a) => ({
        ...a,
        tool: toolIcon(str(p.tool) ?? ""),
        toolUntil: now + TIMERS.tool,
      }));
    case "task.step.completed": {
      const to = nextRoom(str(p.step), str(p.verdict));
      return agent && to ? put(model, errandTo(model, agent, to)) : model;
    }
    case "gate.opened": {
      let next = model;
      for (const id of gateAgents(state, p)) {
        next = update(next, next.avatars[id], (a) => ({ ...a, blockedBy: str(p.gate_id) }));
      }
      return next;
    }
    case "gate.decided":
    case "gate.expired":
    case "question.answered": {
      const gate = str(p.gate_id);
      let next = model;
      for (const a of Object.values(model.avatars)) {
        const clears =
          a.blockedBy === gate || (event.type === "gate.decided" && a.blockedBy === "security");
        if (clears) next = put(next, { ...a, blockedBy: null });
      }
      return next;
    }
    case "security.turn_blocked":
      return update(model, agent, (a) => ({ ...a, blockedBy: "security" }));
    case "security.violation":
      return update(model, agent, (a) => ({ ...a, alarmUntil: now + TIMERS.alarm }));
    case "release.delivered": {
      let next = model;
      for (const a of Object.values(model.avatars)) {
        if (a.room === "release_dock" && !a.walking) {
          next = put(next, { ...a, celebrateUntil: now + TIMERS.celebrate });
        }
      }
      return next;
    }
    default:
      return model;
  }
}

export function reduceOffice(
  model: OfficeModel,
  event: EventEnvelope,
  state: ProjectState,
  now: number,
): OfficeModel {
  return reduceObjects(reduceAvatars(model, event, state, now), event, state, now);
}

/** The scene reports that an avatar reached its target cell. */
export function arrive(model: OfficeModel, agentId: string): OfficeModel {
  const avatar = model.avatars[agentId];
  if (!avatar || !avatar.walking) return model;
  if (avatar.leaving) {
    const avatars = { ...model.avatars };
    delete avatars[agentId];
    return { ...model, avatars };
  }
  // After an errand the avatar walks back to where the truth says it is.
  if (avatar.errand) return put(model, { ...avatar, errand: null, walking: true });
  return put(model, { ...avatar, walking: false, hurry: false });
}

/** Keep the office consistent with the store (live joins, missed events): add, release. */
export function reconcile(model: OfficeModel, state: ProjectState, now: number): OfficeModel {
  let next = model;
  for (const agent of Object.values(state.agents)) {
    const avatar = next.avatars[agent.id];
    if (agent.status === "released") {
      if (avatar && !avatar.leaving) next = put(next, leave(avatar));
      continue;
    }
    if (!avatar) {
      // Idle agents rest in the break room; the others are where the store says.
      const room = agent.status === "idle" ? IDLE : agent.room;
      next = put(next, {
        ...newAvatar(next, agent.id, room, now),
        working: agent.status === "working",
        turnId: agent.turnId,
        purpose: agent.purpose,
        blockedBy: agent.status === "blocked" ? "status" : null,
      });
    }
  }
  return next;
}

/** Seeding from history: everyone already where the events left them (no walk on open). */
export function settle(model: OfficeModel): OfficeModel {
  const avatars: OfficeModel["avatars"] = {};
  for (const avatar of Object.values(model.avatars)) {
    if (avatar.leaving) continue;
    avatars[avatar.id] = {
      ...avatar,
      walking: false,
      hurry: false,
      errand: null,
      origin: avatar.cell,
    };
  }
  return { ...model, avatars };
}
