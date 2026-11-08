// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { Suspense, lazy, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys } from "../../../api/queries.ts";
import { StatusDot } from "../../../components/Badges.tsx";
import { ComingSoon, EmptyState, ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { eur } from "../../../utils/format.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import { AgentAvatar } from "../panels/TeamNow.tsx";
import { TurnDrawer } from "../panels/TurnDrawer.tsx";

const AgentDrawer = lazy(() => import("../panels/AgentDrawer.tsx"));

export function TeamTab() {
  const { t } = useTranslation();
  const projectId = useProjectStore((s) => s.projectId ?? "");
  const live = useProjectStore((s) => s.agents);
  const [open, setOpen] = useState<string | null>(null);
  const [turn, setTurn] = useState<string | null>(null);
  const agents = useQuery({
    queryKey: keys.agents(projectId),
    queryFn: () => api.agents(projectId),
  });
  if (agents.isPending) return <LoadingBlock />;
  if (agents.isError)
    return <ErrorState error={agents.error} onRetry={() => void agents.refetch()} />;
  const rows = agents.data.results.filter((a) => a.status !== "released");
  if (rows.length === 0) return <EmptyState title={t("team.emptyBeforeStart")} />;
  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-card border border-line bg-surface shadow-card">
        <table className="w-full min-w-[48rem] text-sm">
          <caption className="sr-only">{t("team.title")}</caption>
          <thead className="text-left text-xs text-muted uppercase">
            <tr>
              {[
                "agent",
                "package",
                "source",
                "profile",
                "room",
                "status",
                "turns",
                "spent",
                "tools",
              ].map((c) => (
                <th key={c} scope="col" className="px-3 py-2">
                  {t(`team.col.${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((agent) => {
              const now = live[agent.id];
              const status = now?.status ?? agent.status;
              return (
                <tr key={agent.id}>
                  <td className="px-3 py-2">
                    <span className="flex items-center gap-2">
                      <AgentAvatar role={agent.role} color={now?.color} name={agent.display_name} />
                      {/* The role is already in the package column: only a tooltip here. */}
                      <button
                        type="button"
                        onClick={() => setOpen(agent.id)}
                        title={t(`role.${agent.role}`, { defaultValue: agent.role })}
                        className="text-left font-medium whitespace-nowrap text-accent hover:underline"
                      >
                        {agent.display_name}
                      </button>
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {agent.placeholder ? (
                      <span className="text-blocked">{t("team.placeholder")}</span>
                    ) : (
                      `${agent.package.name}@${agent.package.version}`
                    )}
                  </td>
                  <td className="px-3 py-2">{t(`source.${agent.source}`)}</td>
                  <td className="px-3 py-2">{agent.model_profile}</td>
                  <td className="px-3 py-2">
                    {t(`room.${now?.room ?? agent.room}`, {
                      defaultValue: now?.room ?? agent.room,
                    })}
                  </td>
                  <td className="px-3 py-2">
                    <span className="flex items-center gap-1.5">
                      <StatusDot status={status} />
                      {t(`agentStatus.${status}`)}
                    </span>
                  </td>
                  <td className="px-3 py-2">{agent.turns_count}</td>
                  <td className="px-3 py-2">{eur(agent.spent)}</td>
                  <td className="px-3 py-2 text-xs">
                    {agent.allowed_tools.length ? agent.allowed_tools.join(", ") : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ComingSoon title={t("team.manageSoon")}>{t("team.manageSoonDetail")}</ComingSoon>
      {open ? (
        <Suspense fallback={null}>
          <AgentDrawer
            agentId={open}
            spent={rows.find((a) => a.id === open)?.spent}
            onOpenTurn={setTurn}
            onClose={() => setOpen(null)}
          />
        </Suspense>
      ) : null}
      {turn ? <TurnDrawer turnId={turn} onClose={() => setTurn(null)} /> : null}
    </div>
  );
}
