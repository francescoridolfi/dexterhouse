// SPDX-License-Identifier: AGPL-3.0-or-later
// Task detail (Board card, 3D post-it): description, acceptance, branch, fix iterations.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys, useMe } from "../../../api/queries.ts";
import { Button } from "../../../components/Button.tsx";
import { ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { ConfirmDialog, Drawer } from "../../../components/Overlay.tsx";
import { toastError } from "../../../components/toastStore.ts";
import { can } from "../../../utils/auth.ts";
import { useProjectStore } from "../../../store/projectStore.ts";

export function TaskDrawer({ taskId, onClose }: { taskId: string; onClose: () => void }) {
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
