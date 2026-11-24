// SPDX-License-Identifier: AGPL-3.0-or-later
// One change request: number, title, status, budget, cost, release; actions by role
// (member: edit draft, estimate; admin: queue/start, cancel).
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, ExternalLink } from "lucide-react";
import { Suspense, lazy, useState } from "react";
import { useTranslation } from "react-i18next";

import { type ChangeRequest, e13, e13Keys } from "../../../api/e13.ts";
import { StatusBadge } from "../../../components/Badges.tsx";
import { Button } from "../../../components/Button.tsx";
import { ConfirmDialog } from "../../../components/Overlay.tsx";
import { toastError } from "../../../components/toastStore.ts";
import { eur } from "../../../utils/format.ts";

const Markdown = lazy(() =>
  import("../../../components/code/Markdown.tsx").then((m) => ({ default: m.Markdown })),
);

export function ChangeRequestRow({
  cr,
  member,
  admin,
  projectCompleted,
  onEdit,
}: {
  cr: ChangeRequest;
  member: boolean;
  admin: boolean;
  projectCompleted: boolean;
  onEdit: () => void;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState<"queue" | "cancel" | null>(null);
  const refresh = () =>
    void client.invalidateQueries({ queryKey: e13Keys.changeRequests(cr.project) });
  const action = useMutation({
    mutationFn: (name: "queue" | "cancel") => e13.changeRequestAction(cr.id, name),
    onSuccess: () => setConfirm(null),
    onError: (error) => {
      setConfirm(null);
      toastError(t("cr.actionFailed"), error);
    },
    onSettled: refresh,
  });
  const estimate = useMutation({
    mutationFn: () => e13.estimateChangeRequest(cr.id),
    onError: (error) => toastError(t("cr.estimateFailed"), error),
  });
  const draft = cr.status === "draft";
  const startLabel = projectCompleted ? t("cr.start") : t("cr.queue");
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <ChevronRight
            aria-hidden
            className={`size-4 shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`}
          />
          <span className="shrink-0 font-mono text-xs text-muted">CR-{cr.number}</span>
          <span className="truncate text-sm font-medium">{cr.title}</span>
        </button>
        <StatusBadge status={cr.status} label={t(`cr.status.${cr.status}`)} />
        <span className="text-xs text-muted tabular-nums">
          {t("cr.budgetCost", { budget: eur(cr.budget, 0), cost: eur(cr.cost ?? 0) })}
        </span>
        {cr.release ? (
          cr.release.url ? (
            <a
              href={cr.release.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
            >
              {t("cr.release", { n: cr.release.number })}
              <ExternalLink aria-hidden className="size-3" />
            </a>
          ) : (
            <span className="text-xs">{t("cr.release", { n: cr.release.number })}</span>
          )
        ) : null}
      </div>
      {open ? (
        <div className="os-pop mt-3 space-y-3 pl-6">
          <div className="text-sm">
            <Suspense fallback={null}>
              <Markdown source={cr.body} />
            </Suspense>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {member && draft ? (
              <Button size="sm" className="rounded-full px-3" onClick={onEdit}>
                {t("cr.edit")}
              </Button>
            ) : null}
            {member && (draft || cr.status === "queued") ? (
              <Button
                size="sm"
                className="rounded-full px-3"
                busy={estimate.isPending}
                onClick={() => estimate.mutate()}
              >
                {t("cr.estimate")}
              </Button>
            ) : null}
            {admin && draft ? (
              <Button
                size="sm"
                variant="primary"
                className="rounded-full px-3"
                onClick={() => setConfirm("queue")}
              >
                {startLabel}
              </Button>
            ) : null}
            {admin && (draft || cr.status === "queued") ? (
              <Button size="sm" className="rounded-full px-3" onClick={() => setConfirm("cancel")}>
                {t("cr.cancel")}
              </Button>
            ) : null}
            {estimate.data ? (
              <span role="status" className="text-xs text-muted">
                {t("cr.estimateResult", {
                  low: eur(estimate.data.low, 0),
                  high: eur(estimate.data.high, 0),
                })}
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
      {confirm ? (
        <ConfirmDialog
          danger={confirm === "cancel"}
          title={
            confirm === "queue"
              ? t(projectCompleted ? "cr.startTitle" : "cr.queueTitle", { n: cr.number })
              : t("cr.cancelTitle", { n: cr.number })
          }
          message={
            confirm === "queue"
              ? t(projectCompleted ? "cr.startMessage" : "cr.queueMessage", {
                  budget: eur(cr.budget, 0),
                })
              : t("cr.cancelMessage")
          }
          confirmLabel={confirm === "queue" ? startLabel : t("cr.cancel")}
          busy={action.isPending}
          onConfirm={() => action.mutate(confirm)}
          onCancel={() => setConfirm(null)}
        />
      ) : null}
    </li>
  );
}
