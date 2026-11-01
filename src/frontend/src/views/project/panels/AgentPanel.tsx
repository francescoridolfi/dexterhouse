// SPDX-License-Identifier: AGPL-3.0-or-later
// Agent detail: current turn, last 10 events, tools used, cost. Same component in the Team
// tab (drawer) and in the 3D office (side panel): nothing is only in 3D (NFR-U3).
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { EventEnvelope } from "../../../api/types.ts";
import { StatusDot } from "../../../components/Badges.tsx";
import type { AgentView, TaskView } from "../../../store/model.ts";
import { agentActivity } from "../../../utils/agentActivity.ts";
import { TONE_CLASS, describeEvent } from "../../../utils/events.ts";
import { duration, eur, integer, time } from "../../../utils/format.ts";
import { useNow } from "../../../utils/useNow.ts";
import { AgentAvatar } from "./TeamNow.tsx";

export function AgentDetails({
  agent,
  events,
  tasks,
  now,
  spent,
  onOpenTurn,
}: {
  agent: AgentView;
  events: EventEnvelope[];
  tasks: Record<string, TaskView>;
  /** Wall time in ms of the replay position; the live clock when omitted. */
  now?: number;
  /** Total from the REST team list when known (events in memory are the last 2 000). */
  spent?: string | null;
  onOpenTurn: (turnId: string) => void;
}) {
  const { t } = useTranslation();
  const ticking = useNow();
  const at = now ?? ticking;
  const activity = useMemo(
    () => agentActivity(events, agent.id, agent.turnId),
    [events, agent.id, agent.turnId],
  );
  const task = Object.values(tasks).find(
    (x) => x.assigned_agent === agent.id && x.status === "in_progress",
  );
  const turn = activity.currentTurn;
  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-center gap-3">
        <AgentAvatar role={agent.role} color={agent.color} name={agent.displayName} />
        <div>
          <p className="font-semibold">{agent.displayName}</p>
          <p className="text-xs text-muted">
            {t(`role.${agent.role}`, { defaultValue: agent.role })} ·{" "}
            {t(`room.${agent.room}`, { defaultValue: agent.room })}
          </p>
        </div>
        <span className="ml-auto flex items-center gap-1.5">
          <StatusDot status={agent.status} />
          {t(`agentStatus.${agent.status}`)}
        </span>
      </div>
      <section aria-labelledby={`turn-${agent.id}`}>
        <h3 id={`turn-${agent.id}`} className="font-semibold">
          {t("agentPanel.currentTurn")}
        </h3>
        {agent.turnId ? (
          <dl className="mt-1 grid grid-cols-2 gap-1">
            <dt className="text-muted">{t("agentPanel.purpose")}</dt>
            <dd>{agent.purpose ?? "—"}</dd>
            <dt className="text-muted">{t("turn.duration")}</dt>
            <dd>{turn ? duration(Math.max(0, (at - Date.parse(turn.startedAt)) / 1000)) : "—"}</dd>
            <dt className="text-muted">{t("agentPanel.tokensEst")}</dt>
            <dd>{turn?.inputTokensEst != null ? integer(turn.inputTokensEst) : "—"}</dd>
            {task ? (
              <>
                <dt className="text-muted">{t("agentPanel.task")}</dt>
                <dd>
                  {task.external_id} {task.title}
                </dd>
              </>
            ) : null}
            <dd className="col-span-2">
              <button
                type="button"
                className="text-accent underline"
                onClick={() => onOpenTurn(agent.turnId!)}
              >
                {t("log.openTurn")}
              </button>
            </dd>
          </dl>
        ) : (
          <p className="text-muted">{t("agentPanel.noTurn")}</p>
        )}
      </section>
      <dl className="grid grid-cols-2 gap-1">
        <dt className="text-muted">{t("agentPanel.cost")}</dt>
        <dd>{eur(spent ?? activity.cost)}</dd>
        <dt className="text-muted">{t("agentPanel.turns")}</dt>
        <dd>{activity.turns}</dd>
      </dl>
      <section>
        <h3 className="font-semibold">{t("agentPanel.tools")}</h3>
        {activity.tools.length === 0 ? (
          <p className="text-muted">—</p>
        ) : (
          <ul className="mt-1 flex flex-wrap gap-1 font-mono text-xs">
            {activity.tools.map((x) => (
              <li key={x.tool} className="rounded-full bg-bg px-2 py-0.5">
                {x.tool} ×{x.count}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h3 className="font-semibold">{t("agentPanel.recent")}</h3>
        <ol className="mt-1 divide-y divide-line font-mono text-xs">
          {activity.recent.map((event) => {
            const line = describeEvent(event, t, tasks);
            const turnId = typeof event.payload.turn_id === "string" ? event.payload.turn_id : null;
            return (
              <li key={event.id} className="flex gap-2 py-1">
                <time className="text-muted">{time(event.created_at)}</time>
                <span aria-hidden>{line.icon}</span>
                <span className={`flex-1 ${TONE_CLASS[line.tone]}`}>{line.text}</span>
                {turnId && event.type.startsWith("agent.turn.") ? (
                  <button
                    type="button"
                    className="text-accent underline"
                    onClick={() => onOpenTurn(turnId)}
                  >
                    {t("agentPanel.turn")}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
