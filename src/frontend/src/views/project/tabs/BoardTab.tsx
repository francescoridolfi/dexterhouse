// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys } from "../../../api/queries.ts";
import { EmptyState } from "../../../components/Feedback.tsx";
import { eur } from "../../../utils/format.ts";
import type { TaskView } from "../../../store/model.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import { BOARD_COLUMNS, boardColumns } from "../../../store/selectors.ts";
import { TaskDrawer } from "../panels/TaskDrawer.tsx";

function useTaskCosts(projectId: string) {
  const costs = useQuery({ queryKey: keys.costs(projectId), queryFn: () => api.costs(projectId) });
  return new Map((costs.data?.by_task ?? []).map((row) => [row.task_id, row.cost]));
}

export function TaskCard({
  task,
  cost,
  onOpen,
}: {
  task: TaskView;
  cost?: string;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  const spent = task.cost ?? cost;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-card border border-line bg-surface p-2.5 text-left text-sm shadow-card hover:border-accent"
    >
      <span className="font-mono text-xs text-muted">{task.external_id}</span>
      <span className="block font-medium">{task.title}</span>
      <span className="mt-1 flex flex-wrap gap-x-2 text-xs text-muted">
        <span>{task.estimate}</span>
        <span>{t(`role.${task.assigned_role}`, { defaultValue: task.assigned_role })}</span>
        <span>{t("board.iteration", { n: task.iteration, max: task.max_iterations })}</span>
        {spent ? <span>{eur(spent)}</span> : null}
      </span>
    </button>
  );
}

export function BoardTab() {
  const { t } = useTranslation();
  const state = useProjectStore();
  const columns = boardColumns(state);
  const costs = useTaskCosts(state.projectId ?? "");
  const [open, setOpen] = useState<string | null>(null);
  if (Object.keys(state.tasks).length === 0) return <EmptyState title={t("board.empty")} />;
  return (
    <>
      <div className="grid gap-3 md:auto-cols-[minmax(13rem,1fr)] md:grid-flow-col md:overflow-x-auto">
        {BOARD_COLUMNS.map((column) => (
          <section
            key={column.id}
            aria-labelledby={`col-${column.id}`}
            className="rounded-card bg-surface/60 p-2"
          >
            <h2
              id={`col-${column.id}`}
              className="mb-2 flex justify-between px-1 text-xs font-semibold tracking-wide text-muted uppercase"
            >
              {t(`board.column.${column.id}`)}
              <span>{columns[column.id]?.length ?? 0}</span>
            </h2>
            <ul className="space-y-2">
              {(columns[column.id] ?? []).map((task) => (
                <li key={task.id}>
                  <TaskCard task={task} cost={costs.get(task.id)} onOpen={() => setOpen(task.id)} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      {open ? <TaskDrawer taskId={open} onClose={() => setOpen(null)} /> : null}
    </>
  );
}
