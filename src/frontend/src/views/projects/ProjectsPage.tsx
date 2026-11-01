// SPDX-License-Identifier: AGPL-3.0-or-later
import { Bell, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { Project } from "../../api/types.ts";
import { useProjects } from "../../api/queries.ts";
import { BudgetBar, ModeBadge, StatusBadge } from "../../components/Badges.tsx";
import { EmptyState, ErrorState, Skeleton } from "../../components/Feedback.tsx";
import { dateTime } from "../../utils/format.ts";
import { sortProjects } from "../../utils/projects.ts";

function PhaseLine({ project }: { project: Project }) {
  const { t } = useTranslation();
  if (project.status === "completed") return <span>{dateTime(project.completed_at)}</span>;
  if (project.status === "waiting" && project.waiting_reason === "budget") {
    return <span className="text-failed">▸ {t("projects.budgetExceeded")}</span>;
  }
  if (project.current_phases.length === 0) return <span className="text-muted">—</span>;
  return (
    <span>
      ▸ {project.current_phases.map((p) => t(`phase.${p}`, { defaultValue: p })).join(", ")}
    </span>
  );
}

export function ProjectsPage() {
  const { t } = useTranslation();
  const [status, setStatus] = useState("");
  const [mode, setMode] = useState("");
  const [q, setQ] = useState("");
  const projects = useProjects({ status, execution_mode: mode, q });
  const rows = useMemo(() => sortProjects(projects.data?.results ?? []), [projects.data]);
  const filtered = status || mode || q;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-2xl font-semibold">{t("projects.title")}</h1>
        <label className="sr-only" htmlFor="filter-status">
          {t("projects.filterStatus")}
        </label>
        <select
          id="filter-status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="min-h-11 rounded-card border border-line bg-surface px-2 text-sm"
        >
          <option value="">{t("projects.allStatuses")}</option>
          {["draft", "running", "waiting", "paused", "completed", "failed", "archived"].map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="filter-mode">
          {t("projects.filterMode")}
        </label>
        <select
          id="filter-mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="min-h-11 rounded-card border border-line bg-surface px-2 text-sm"
        >
          <option value="">{t("projects.allModes")}</option>
          <option value="supervised">{t("mode.supervised")}</option>
          <option value="autonomous">{t("mode.autonomous")}</option>
        </select>
        <div className="relative">
          <Search
            aria-hidden
            className="pointer-events-none absolute top-3.5 left-2.5 size-4 text-muted"
          />
          <input
            type="search"
            aria-label={t("projects.search")}
            placeholder={t("projects.search")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="min-h-11 w-48 rounded-card border border-line bg-surface pr-2 pl-8 text-sm"
          />
        </div>
        <Link
          to="/projects/new"
          className="inline-flex min-h-11 items-center gap-2 rounded-card bg-accent px-4 font-medium text-white"
        >
          <Plus aria-hidden className="size-4" />
          {t("projects.new")}
        </Link>
      </div>

      <section
        aria-label={t("projects.title")}
        className="rounded-card border border-line bg-surface shadow-card"
      >
        {projects.isPending ? (
          <div className="p-4" role="status" aria-label={t("loading")}>
            <Skeleton count={4} className="h-10 w-full" />
          </div>
        ) : projects.isError ? (
          <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            title={filtered ? t("projects.noMatch") : t("projects.empty")}
            action={
              filtered ? null : (
                <Link
                  to="/projects/new"
                  className="inline-flex min-h-11 items-center rounded-card bg-accent px-4 text-white"
                >
                  {t("projects.new")}
                </Link>
              )
            }
          />
        ) : (
          <ul className="divide-y divide-line">
            {rows.map((project) => (
              <li key={project.id}>
                <Link
                  to={`/projects/${project.id}`}
                  className="grid justify-items-start gap-2 px-4 py-3 hover:bg-bg md:grid-cols-[minmax(10rem,1.2fr)_auto_auto_minmax(10rem,1.4fr)_auto_auto] md:items-center md:gap-4"
                >
                  <span className="font-medium">{project.name}</span>
                  <ModeBadge mode={project.execution_mode} />
                  <StatusBadge status={project.status} />
                  <span className="truncate text-sm">
                    <PhaseLine project={project} />
                  </span>
                  <BudgetBar spent={project.spent} budget={project.budget} compact />
                  <span
                    className="flex min-w-10 items-center gap-1 text-sm"
                    aria-label={t("projects.openGates", { count: project.open_gates_count })}
                  >
                    {project.open_gates_count > 0 ? (
                      <>
                        <Bell aria-hidden className="size-4 text-blocked" />
                        {project.open_gates_count}
                      </>
                    ) : null}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
