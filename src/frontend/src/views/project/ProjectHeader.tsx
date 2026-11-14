// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronLeft,
  CodeXml,
  Loader2,
  Pause,
  Pencil,
  Play,
  RotateCcw,
  X,
} from "lucide-react";
import { type FormEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints.ts";
import { useMe } from "../../api/queries.ts";
import { AmountField } from "../../components/AmountField.tsx";
import { BudgetBar, ModeBadge, StatusDot } from "../../components/Badges.tsx";
import { Button } from "../../components/Button.tsx";
import { codeHref } from "../code/links.ts";
import { ConfirmDialog } from "../../components/Overlay.tsx";
import { toastError, toastSuccess } from "../../components/toastStore.ts";
import { can } from "../../utils/auth.ts";
import { formatAmount, parseAmount } from "../../utils/amount.ts";
import { eur } from "../../utils/format.ts";
import { useProjectStore } from "../../store/projectStore.ts";

function ConnectionIndicator() {
  const { t } = useTranslation();
  const connection = useProjectStore((s) => s.connection);
  const live = connection === "live";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted" role="status">
      <span
        aria-hidden
        className={`size-1.5 rounded-full ${live ? "bg-done shadow-[0_0_6px] shadow-done" : "animate-pulse bg-blocked"}`}
      />
      {t(`connection.${connection}`)}
    </span>
  );
}

/** Inline budget editor: one recessed capsule (− € amount +), confirm and cancel. */
export function BudgetEditor({ onDone }: { onDone: () => void }) {
  const { t, i18n } = useTranslation();
  const project = useProjectStore((s) => s.project);
  const spent = Number(useProjectStore((s) => s.budget.spent) ?? 0);
  const initial = project?.budget ? Number(project.budget) : 0;
  const [value, setValue] = useState(project?.budget ? formatAmount(initial, i18n.language) : "");
  const amount = parseAmount(value);
  const warningId = useId();
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: () => api.updateProject(project?.id ?? "", { budget: String(amount ?? 0) }),
    onSuccess: () => {
      toastSuccess(t("budget.saved"));
      void client.invalidateQueries({ queryKey: ["projects"] });
      onDone();
    },
    onError: (error) => toastError(t("budget.saveFailed"), error),
  });
  const valid = amount !== null;
  const changed = valid && amount !== initial;
  const below = valid && amount < spent;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (changed) save.mutate();
    else onDone();
  };
  const round =
    "grid size-7 shrink-0 place-items-center rounded-full transition-colors disabled:opacity-40";
  return (
    <form
      onSubmit={submit}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onDone();
        }
      }}
      className="os-pop flex flex-wrap items-center gap-1.5"
    >
      <AmountField
        label={t("budget.new")}
        value={value}
        onChange={setValue}
        describedBy={below ? warningId : undefined}
        decreaseLabel={t("budget.decrease")}
        increaseLabel={t("budget.increase")}
        inputProps={{ autoFocus: true }}
      />
      <button
        type="submit"
        aria-label={t("save")}
        title={t("save")}
        disabled={!valid || save.isPending}
        className={`${round} os-pressable bg-gradient-to-b from-[#3d9bff] to-accent text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.3),0_4px_10px_-4px_rgb(10_132_255/0.7)] hover:brightness-110`}
      >
        {save.isPending ? (
          <Loader2 aria-hidden className="size-3.5 animate-spin" />
        ) : (
          <Check aria-hidden className="size-3.5" strokeWidth={3} />
        )}
      </button>
      <button
        type="button"
        aria-label={t("cancel")}
        title={t("cancel")}
        onClick={onDone}
        className={`${round} os-pressable bg-white/8 text-muted hover:bg-white/14 hover:text-fg`}
      >
        <X aria-hidden className="size-3.5" strokeWidth={2.5} />
      </button>
      {below ? (
        <p id={warningId} role="status" className="basis-full pl-3 text-xs text-budget-warn">
          {t("budget.belowSpent", { spent: eur(spent) })}
        </p>
      ) : null}
    </form>
  );
}

export function ProjectHeader() {
  const { t } = useTranslation();
  const me = useMe();
  const project = useProjectStore((s) => s.project);
  const budget = useProjectStore((s) => s.budget);
  const [editing, setEditing] = useState(false);
  const [confirmPause, setConfirmPause] = useState(false);
  const [explainMode, setExplainMode] = useState(false);
  const action = useMutation({
    mutationFn: (name: "pause" | "resume" | "retry" | "start") =>
      api.projectAction(project?.id ?? "", name),
    onSuccess: () => setConfirmPause(false),
    onError: (error) => {
      setConfirmPause(false);
      toastError(t("project.actionFailed"), error);
    },
  });
  if (!project) return null;
  const member = can(me.data, "member");
  const status =
    project.status === "waiting" && project.waiting_reason
      ? `waiting_${project.waiting_reason}`
      : project.status;

  return (
    <header className="flex flex-wrap items-center gap-x-3 gap-y-3">
      <Link
        to="/projects"
        aria-label={t("nav.projects")}
        title={t("nav.projects")}
        className="os-pressable grid size-8 shrink-0 place-items-center rounded-full bg-white/8 text-muted shadow-[inset_0_1px_0_rgb(255_255_255/0.1)] hover:bg-white/14 hover:text-fg"
      >
        <ChevronLeft aria-hidden className="size-4.5" strokeWidth={2.5} />
      </Link>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[22px] leading-tight font-semibold tracking-tight">
          {project.name}
        </h1>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
          <ModeBadge
            tinted
            mode={project.execution_mode}
            onClick={() => setExplainMode(!explainMode)}
          />
          <span className="inline-flex items-center gap-1.5">
            <StatusDot status={project.status} className="size-2" />
            {t(`status.${status}`, { defaultValue: project.status })}
          </span>
          <span aria-hidden>·</span>
          <ConnectionIndicator />
        </div>
      </div>
      <div className="order-last flex basis-full items-center gap-1 rounded-full bg-black/20 py-1 pr-1 pl-3.5 shadow-[inset_0_1px_2px_rgb(0_0_0/0.25)] @2xl:order-none @2xl:basis-auto">
        {editing ? null : (
          <div className="min-w-0 flex-1 [&>div]:min-w-40">
            <BudgetBar spent={budget.spent} budget={budget.budget} />
          </div>
        )}
        {member && !editing ? (
          <button
            type="button"
            aria-label={t("budget.edit")}
            title={t("budget.edit")}
            onClick={() => setEditing(true)}
            className="grid size-7 place-items-center rounded-full text-muted hover:bg-white/10 hover:text-fg"
          >
            <Pencil aria-hidden className="size-3.5" />
          </button>
        ) : null}
        {editing ? <BudgetEditor onDone={() => setEditing(false)} /> : null}
      </div>
      <div className="flex items-center gap-2">
        <Link
          to={codeHref(project.id)}
          title={t("codeApp.open")}
          className="os-pressable inline-flex min-h-8 items-center gap-1.5 rounded-full border border-white/10 bg-white/8 px-3.5 text-sm font-medium shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] hover:bg-white/14"
        >
          <CodeXml aria-hidden className="size-3.5" />
          {t("codeApp.short")}
        </Link>
        {member && project.status === "draft" ? (
          <Button
            size="sm"
            variant="primary"
            className="rounded-full px-3.5"
            icon={<Play aria-hidden className="size-3.5" />}
            busy={action.isPending}
            onClick={() => action.mutate("start")}
          >
            {t("project.start")}
          </Button>
        ) : null}
        {member && (project.status === "running" || project.status === "waiting") ? (
          <Button
            size="sm"
            className="rounded-full px-3.5"
            icon={<Pause aria-hidden className="size-3.5" />}
            onClick={() => setConfirmPause(true)}
          >
            {t("project.pause")}
          </Button>
        ) : null}
        {member && project.status === "paused" ? (
          <Button
            size="sm"
            variant="primary"
            className="rounded-full px-3.5"
            icon={<Play aria-hidden className="size-3.5" />}
            busy={action.isPending}
            onClick={() => action.mutate("resume")}
          >
            {t("project.resume")}
          </Button>
        ) : null}
        {can(me.data, "admin") && project.status === "failed" ? (
          <Button
            size="sm"
            className="rounded-full px-3.5"
            icon={<RotateCcw aria-hidden className="size-3.5" />}
            busy={action.isPending}
            onClick={() => action.mutate("retry")}
          >
            {t("project.retry")}
          </Button>
        ) : null}
      </div>
      {explainMode ? (
        <p role="note" className="os-pop w-full rounded-[14px] bg-white/6 px-4 py-3 text-sm">
          {t(`mode.${project.execution_mode}Help`)} {t("mode.changeOnlyDraft")}
        </p>
      ) : null}
      {confirmPause ? (
        <ConfirmDialog
          title={t("project.pauseTitle")}
          message={t("project.pauseMessage")}
          confirmLabel={t("project.pause")}
          busy={action.isPending}
          onConfirm={() => action.mutate("pause")}
          onCancel={() => setConfirmPause(false)}
        />
      ) : null}
      {budget.orgExceeded ? (
        <p role="alert" className="w-full rounded-card bg-failed/10 p-2 text-sm text-failed">
          {t("budget.orgExceeded")}{" "}
          <Link to="/settings/budget" className="underline">
            {t("budget.openSettings")}
          </Link>
        </p>
      ) : null}
    </header>
  );
}
