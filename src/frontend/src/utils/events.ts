// SPDX-License-Identifier: AGPL-3.0-or-later
// One readable line per event for the live log and the timeline (no domain logic: wording).
import type { TFunction } from "i18next";

import type { EventEnvelope } from "../api/types.ts";
import { duration, eur } from "./format.ts";

export type Tone = "info" | "ok" | "warn" | "error" | "tool" | "note";

export interface EventLine {
  icon: string;
  text: string;
  tone: Tone;
}

const s = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
};

export function describeEvent(
  event: EventEnvelope,
  t: TFunction,
  tasks: Record<string, { external_id: string }> = {},
): EventLine {
  const p = event.payload;
  const task = tasks[s(p.task_id)]?.external_id ?? "";
  switch (event.type) {
    case "agent.turn.started":
      return { icon: "▶", tone: "info", text: t("events.turnStarted", { purpose: s(p.purpose) }) };
    case "agent.turn.completed":
      return {
        icon: "✓",
        tone: "ok",
        text: t("events.turnCompleted", {
          cost: eur(s(p.cost)),
          duration: duration(Number(p.duration_s)),
        }),
      };
    case "agent.turn.failed":
      return { icon: "✗", tone: "error", text: t("events.turnFailed", { code: s(p.error_code) }) };
    case "agent.tool.requested":
      return { icon: "▶", tone: "tool", text: s(p.tool) };
    case "agent.tool.used":
      return {
        icon: p.allowed === false ? "⛔" : "⚙",
        tone: p.allowed === false ? "error" : "tool",
        text: t("events.toolUsed", { tool: s(p.tool), ms: Math.round(Number(p.duration_ms) || 0) }),
      };
    case "agent.skill.loaded":
      return { icon: "📖", tone: "info", text: t("events.skillLoaded", { skill: s(p.skill) }) };
    case "agent.hired":
      return { icon: "＋", tone: "info", text: t("events.hired", { name: s(p.display_name) }) };
    case "phase.started":
      return {
        icon: "●",
        tone: "info",
        text: t("events.phaseStarted", {
          phase: t(`phase.${s(p.phase_id)}`, { defaultValue: s(p.phase_id) }),
        }),
      };
    case "phase.completed":
      return {
        icon: "✓",
        tone: "ok",
        text: t("events.phaseCompleted", {
          phase: t(`phase.${s(p.phase_id)}`, { defaultValue: s(p.phase_id) }),
          cost: eur(s(p.cost)),
        }),
      };
    case "phase.reopened":
      return { icon: "↻", tone: "warn", text: t("events.phaseReopened", { phase: s(p.phase_id) }) };
    case "task.started":
      return { icon: "▶", tone: "info", text: t("events.taskStarted", { task }) };
    case "task.iteration":
      return {
        icon: "↻",
        tone: "warn",
        text: t("events.taskIteration", {
          task,
          n: s(p.iteration),
          max: s(p.max_iterations),
          reason: s(p.reason),
        }),
      };
    case "task.step.completed":
      return {
        icon: p.verdict === "fail" || p.verdict === "request_changes" ? "✗" : "✓",
        tone: p.verdict === "fail" ? "error" : "ok",
        text: t("events.taskStep", { task, step: s(p.step), verdict: s(p.verdict) }),
      };
    case "task.completed":
      return {
        icon: "✓",
        tone: "ok",
        text: t("events.taskCompleted", { task, cost: eur(s(p.cost)) }),
      };
    case "task.escalated":
      return { icon: "⚠", tone: "error", text: t("events.taskEscalated", { task }) };
    case "gate.opened":
      return { icon: "🔔", tone: "warn", text: t("events.gateOpened", { title: s(p.title) }) };
    case "gate.decided":
      return {
        icon: "✔",
        tone: "ok",
        text: t("events.gateDecided", {
          decision: s(p.decision),
          by: s((p.decided_by as { name?: string } | null)?.name ?? t("events.system")),
        }),
      };
    case "question.answered":
      return { icon: "✔", tone: "ok", text: t("events.answered") };
    case "note.added":
      return { icon: "📝", tone: "note", text: s(p.excerpt) };
    case "note.consumed":
      return { icon: "📝", tone: "note", text: t("events.noteRead") };
    case "budget.warning":
      return { icon: "💡", tone: "warn", text: t("events.budgetWarning", { pct: s(p.pct) }) };
    case "budget.exceeded":
      return {
        icon: "🛑",
        tone: "error",
        text: t("events.budgetExceeded", { spent: eur(s(p.spent)), budget: eur(s(p.budget)) }),
      };
    case "test.run.completed":
      return {
        icon: p.ok ? "✓" : "✗",
        tone: p.ok ? "ok" : "error",
        text: t("events.tests", { passed: s(p.passed), failed: s(p.failed) }),
      };
    case "security.violation":
      return {
        icon: "⛔",
        tone: "error",
        text: t("events.violation", { tool: s(p.tool), kind: s(p.kind) }),
      };
    case "project.waiting":
      return {
        icon: "⏸",
        tone: "warn",
        text: t("events.waiting", {
          reason: t(`waiting.${s(p.reason)}`, { defaultValue: s(p.reason) }),
        }),
      };
    default:
      return {
        icon: "·",
        tone: "info",
        text: t(`eventType.${event.type}`, { defaultValue: event.type }),
      };
  }
}

export const TONE_CLASS: Record<Tone, string> = {
  info: "",
  ok: "text-done",
  warn: "text-blocked",
  error: "text-failed",
  tool: "text-muted",
  note: "text-supervised",
};

/** Who an event is about: the agent's display name, the user, or "system". */
export function actorLabel(
  event: EventEnvelope,
  agents: Record<string, { displayName: string }>,
  t: TFunction,
): string {
  const agentId =
    s(event.payload.agent_id) || (event.actor.type === "agent" ? s(event.actor.id) : "");
  if (agentId && agents[agentId]) return agents[agentId].displayName;
  if (event.actor.type === "system") return t("events.system");
  return event.actor.name ?? event.actor.type;
}
