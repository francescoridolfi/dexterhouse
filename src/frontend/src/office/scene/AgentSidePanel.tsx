// SPDX-License-Identifier: AGPL-3.0-or-later
// Click on an avatar: the 2D agent panel on the right (480 px); the scene shrinks, it is not
// covered (ux_3d_office.md). Same component as the Team tab.
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/endpoints.ts";
import { keys } from "../../api/queries.ts";
import { AgentDetails } from "../../views/project/panels/AgentPanel.tsx";
import { useOffice, useProject, useRuntime } from "./context.ts";

export function AgentSidePanel({ onOpenTurn }: { onOpenTurn: (turnId: string) => void }) {
  const { t } = useTranslation();
  const { runtime, replay, wallTime } = useOffice();
  const selected = useRuntime((s) => s.selected);
  const agent = useProject((s) => (selected ? s.agents[selected] : undefined));
  const events = useProject((s) => s.events);
  const tasks = useProject((s) => s.tasks);
  const projectId = useProject((s) => s.projectId ?? "");
  const team = useQuery({
    queryKey: keys.agents(projectId),
    queryFn: () => api.agents(projectId),
    enabled: !!agent && !replay,
  });
  if (!agent) return null;
  return (
    <aside
      aria-label={agent.displayName}
      className="flex w-[480px] max-w-[55%] shrink-0 flex-col border-l border-line"
    >
      <header className="flex items-center justify-between border-b border-line p-3">
        <h2 className="font-semibold">{agent.displayName}</h2>
        <button
          type="button"
          aria-label={t("close")}
          onClick={() => runtime.getState().select(null)}
          className="grid size-9 place-items-center rounded-card hover:bg-bg"
        >
          <X aria-hidden className="size-5" />
        </button>
      </header>
      <div className="flex-1 overflow-y-auto p-4">
        <AgentDetails
          agent={agent}
          events={events}
          tasks={tasks}
          now={replay ? wallTime() : undefined}
          spent={replay ? undefined : team.data?.results.find((a) => a.id === agent.id)?.spent}
          onOpenTurn={onOpenTurn}
        />
      </div>
    </aside>
  );
}
