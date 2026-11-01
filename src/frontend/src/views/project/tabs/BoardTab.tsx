// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys, useMe } from "../../../api/queries.ts";
import { Button } from "../../../components/Button.tsx";
import { EmptyState, ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { ConfirmDialog, Drawer } from "../../../components/Overlay.tsx";
import { toastError } from "../../../components/toastStore.ts";
import { can } from "../../../utils/auth.ts";
import { eur } from "../../../utils/format.ts";
import type { TaskView } from "../../../store/model.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import { BOARD_COLUMNS, boardColumns } from "../../../store/selectors.ts";

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

function TaskDrawer({ taskId, onClose }: { taskId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const me = useMe();
  const task = useQuery({ queryKey: keys.task(taskId), queryFn: () => api.task(taskId) });
  const live = useProjectStore((s) => s.tasks[taskId]);
  const tasks = useProjectStore((s) => s.tasks);
  const [confirm, setConfirm] = useState(false);
  const cancel = useMutation({
    mutationFn: () => api.cancelTask(taskId),
    onSuccess: () => {
      setConfirm(false);
      onClose();
    },
    onError: (error) => {
      setConfirm(false);
      toastError(t("board.cancelFailed"), error);
    },
  });
  const data = task.data;
  const status = live?.status ?? data?.status;
  return (
    <Drawer
      title={data ? `${data.external_id} · ${data.title}` : t("loading")}
      onClose={onClose}
      wide
      footer={
        can(me.data, "admin") && status && ["pending", "ready", "escalated"].includes(status) ? (
          <Button variant="danger" onClick={() => setConfirm(true)}>
            {t("board.cancelTask")}
          </Button>
        ) : undefined
      }
    >
      {task.isPending ? (
        <LoadingBlock />
      ) : task.isError ? (
        <ErrorState error={task.error} onRetry={() => void task.refetch()} />
      ) : data ? (
        <div className="space-y-4 text-sm">
          <p className="whitespace-pre-wrap">{data.description || "—"}</p>
          <section>
            <h3 className="font-semibold">{t("board.acceptance")}</h3>
            <ul className="list-disc pl-5">
              {data.acceptance.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
          <dl className="grid grid-cols-2 gap-1">
            <dt className="text-muted">{t("board.status")}</dt>
            <dd>{t(`taskStatus.${status ?? "pending"}`)}</dd>
            <dt className="text-muted">{t("board.branch")}</dt>
            <dd className="font-mono">{live?.branch ?? data.branch ?? "—"}</dd>
            <dt className="text-muted">{t("board.dependsOn")}</dt>
            <dd>
              {data.depends_on.map((id) => tasks[id]?.external_id ?? id.slice(0, 8)).join(", ") ||
                "—"}
            </dd>
          </dl>
          <section>
            <h3 className="font-semibold">{t("board.iterations")}</h3>
            {data.children.length === 0 ? (
              <p className="text-muted">{t("board.noFixes")}</p>
            ) : (
              <ol className="space-y-1">
                {data.children.map((child) => (
                  <li key={child.id}>
                    {t("board.iteration", { n: child.iteration, max: child.max_iterations })} ·{" "}
                    {child.title} · {t(`taskStatus.${child.status}`)}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      ) : null}
      {confirm ? (
        <ConfirmDialog
          title={t("board.cancelTask")}
          message={t("board.cancelMessage")}
          confirmLabel={t("board.cancelTask")}
          danger
          busy={cancel.isPending}
          onConfirm={() => cancel.mutate()}
          onCancel={() => setConfirm(false)}
        />
      ) : null}
    </Drawer>
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
