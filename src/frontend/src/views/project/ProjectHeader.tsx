// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Pencil, Play, RotateCcw } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints.ts";
import { useMe } from "../../api/queries.ts";
import { BudgetBar, ModeBadge, StatusBadge } from "../../components/Badges.tsx";
import { Button } from "../../components/Button.tsx";
import { ConfirmDialog } from "../../components/Overlay.tsx";
import { toastError, toastSuccess } from "../../components/toastStore.ts";
import { can } from "../../utils/auth.ts";
import { useProjectStore } from "../../store/projectStore.ts";

function ConnectionIndicator() {
  const { t } = useTranslation();
  const connection = useProjectStore((s) => s.connection);
  const live = connection === "live";
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted" role="status">
      <span
        aria-hidden
        className={`size-2 rounded-full ${live ? "bg-done" : "animate-pulse bg-blocked"}`}
      />
      {t(`connection.${connection}`)}
    </span>
  );
}

export function BudgetEditor({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const project = useProjectStore((s) => s.project);
  const [value, setValue] = useState(project?.budget ? String(Number(project.budget)) : "");
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: () => api.updateProject(project?.id ?? "", { budget: value }),
    onSuccess: () => {
      toastSuccess(t("budget.saved"));
      void client.invalidateQueries({ queryKey: ["projects"] });
      onDone();
    },
    onError: (error) => toastError(t("budget.saveFailed"), error),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="flex items-center gap-1">
      <label htmlFor="budget-input" className="sr-only">
        {t("budget.new")}
      </label>
      <input
        id="budget-input"
        type="number"
        min="0"
        step="0.5"
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="min-h-9 w-24 rounded-card border border-line bg-surface px-2 text-sm"
      />
      <Button type="submit" size="sm" variant="primary" busy={save.isPending}>
        {t("save")}
      </Button>
      <Button size="sm" onClick={onDone}>
        {t("cancel")}
      </Button>
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
    <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <Link to="/projects" className="text-sm text-muted hover:text-fg">
        ← {t("nav.projects")}
      </Link>
      <h1 className="text-xl font-semibold">{project.name}</h1>
      <ModeBadge mode={project.execution_mode} onClick={() => setExplainMode(!explainMode)} />
      <StatusBadge
        status={project.status}
        label={t(`status.${status}`, { defaultValue: project.status })}
      />
      <div className="flex items-center gap-1">
        <BudgetBar spent={budget.spent} budget={budget.budget} />
        {member && !editing ? (
          <button
            type="button"
            aria-label={t("budget.edit")}
            onClick={() => setEditing(true)}
            className="grid size-9 place-items-center rounded-card hover:bg-bg"
          >
            <Pencil aria-hidden className="size-4" />
          </button>
        ) : null}
        {editing ? <BudgetEditor onDone={() => setEditing(false)} /> : null}
      </div>
      <div className="ml-auto flex items-center gap-2">
        <ConnectionIndicator />
        {member && project.status === "draft" ? (
          <Button
            variant="primary"
            icon={<Play aria-hidden className="size-4" />}
            busy={action.isPending}
            onClick={() => action.mutate("start")}
          >
            {t("project.start")}
          </Button>
        ) : null}
        {member && (project.status === "running" || project.status === "waiting") ? (
          <Button
            icon={<Pause aria-hidden className="size-4" />}
            onClick={() => setConfirmPause(true)}
          >
            {t("project.pause")}
          </Button>
        ) : null}
        {member && project.status === "paused" ? (
          <Button
            variant="primary"
            icon={<Play aria-hidden className="size-4" />}
            busy={action.isPending}
            onClick={() => action.mutate("resume")}
          >
            {t("project.resume")}
          </Button>
        ) : null}
        {can(me.data, "admin") && project.status === "failed" ? (
          <Button
            icon={<RotateCcw aria-hidden className="size-4" />}
            busy={action.isPending}
            onClick={() => action.mutate("retry")}
          >
            {t("project.retry")}
          </Button>
        ) : null}
      </div>
      {explainMode ? (
        <p role="note" className="w-full rounded-card border border-line bg-surface p-3 text-sm">
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
