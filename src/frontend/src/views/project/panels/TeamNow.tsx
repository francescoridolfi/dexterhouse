// SPDX-License-Identifier: AGPL-3.0-or-later
import { useTranslation } from "react-i18next";

import { StatusDot } from "../../../components/Badges.tsx";
import { Card, EmptyState } from "../../../components/Feedback.tsx";
import { agentColor } from "../../../theme/tokens.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import { teamList } from "../../../store/selectors.ts";

export function AgentAvatar({ role, color, name }: { role: string; color?: string; name: string }) {
  return (
    <span
      aria-hidden="true"
      className="grid size-8 shrink-0 place-items-center rounded-full text-xs font-bold text-black"
      style={{ backgroundColor: agentColor(role, color) }}
    >
      {name.slice(0, 2).toUpperCase()}
    </span>
  );
}

export function TeamNow() {
  const { t } = useTranslation();
  const state = useProjectStore();
  const team = teamList(state);
  return (
    <Card title={t("team.now")}>
      {team.length === 0 ? (
        <EmptyState title={t("team.empty")} />
      ) : (
        <ul className="divide-y divide-line">
          {team.map((agent) => {
            const task = Object.values(state.tasks).find(
              (x) => x.assigned_agent === agent.id && x.status === "in_progress",
            );
            return (
              <li key={agent.id} className="flex items-center gap-3 px-4 py-2">
                <AgentAvatar role={agent.role} color={agent.color} name={agent.displayName} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{agent.displayName}</p>
                  <p className="truncate text-xs text-muted">
                    {t(`room.${agent.room}`, { defaultValue: agent.room })}
                    {agent.purpose ? ` · ${agent.purpose}` : task ? ` · ${task.external_id}` : ""}
                  </p>
                </div>
                <span className="flex items-center gap-1.5 text-xs">
                  <StatusDot status={agent.status} />
                  {t(`agentStatus.${agent.status}`)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
