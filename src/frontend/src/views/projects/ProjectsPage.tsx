// SPDX-License-Identifier: AGPL-3.0-or-later
import { Bell, CircleDot, Plus, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { Project } from "../../api/types.ts";
import { useProjects } from "../../api/queries.ts";
import { BudgetBar, ModeBadge, StatusBadge } from "../../components/Badges.tsx";
import { EmptyState, ErrorState, Skeleton } from "../../components/Feedback.tsx";
import { FilterBar, FilterGroup, FilterSelect, SearchField } from "../../components/FilterBar.tsx";
import { dateTime } from "../../utils/format.ts";
import { sortProjects } from "../../utils/projects.ts";

const ICON_TINTS = [
  ["#5e9bff", "#2c4fe0"],
  ["#c08cff", "#7039e0"],
  ["#48d597", "#0f9c62"],
  ["#ffb340", "#f06a1d"],
  ["#ff6f91", "#d1305c"],
  ["#5ee0e0", "#1b8fa8"],
] as const;

/** Card-mode monogram: a dock-like tile with the project's initials. */
function ProjectIcon({ name }: { name: string }) {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  const [from, to] = ICON_TINTS[hash % ICON_TINTS.length] ?? ICON_TINTS[0];
  const initials = name
    .split(/\s+/)
    .map((word) => word[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <span
      aria-hidden
      className="grid size-10 shrink-0 place-items-center rounded-[12px] text-sm font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.35),0_4px_10px_-4px_rgb(0_0_0/0.6)] @3xl:hidden"
      style={{ background: `linear-gradient(160deg, ${from}, ${to})` }}
    >
      {initials.length > 1 ? initials : name.slice(0, 2).toUpperCase()}
    </span>
  );
}

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
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="order-1 mr-auto text-2xl font-semibold tracking-tight">
          {t("projects.title")}
        </h1>
        <FilterBar className="order-3 basis-full @4xl:order-2 @4xl:max-w-2xl @4xl:flex-1 @4xl:basis-auto">
          <SearchField label={t("projects.search")} value={q} onChange={setQ} />
          <FilterGroup>
            <FilterSelect
              id="filter-status"
              label={t("projects.filterStatus")}
              icon={<CircleDot aria-hidden className="size-3.5" />}
              value={status}
              onChange={setStatus}
              options={[
                ["", t("projects.allStatuses")],
                ...["draft", "running", "waiting", "paused", "completed", "failed", "archived"].map(
                  (s): [string, string] => [s, t(`status.${s}`)],
                ),
              ]}
            />
            <FilterSelect
              id="filter-mode"
              label={t("projects.filterMode")}
              icon={<SlidersHorizontal aria-hidden className="size-3.5" />}
              value={mode}
              onChange={setMode}
              options={[
                ["", t("projects.allModes")],
                ["supervised", t("mode.supervised")],
                ["autonomous", t("mode.autonomous")],
              ]}
            />
          </FilterGroup>
        </FilterBar>
        <Link
          to="/projects/new"
          title={t("projects.new")}
          className="os-pressable order-2 inline-flex h-10 items-center justify-center gap-2 rounded-full bg-gradient-to-b from-[#3d9bff] to-accent px-4 text-sm font-medium text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.3),0_6px_16px_-6px_rgb(10_132_255/0.7)] hover:brightness-110 @max-xl:w-10 @max-xl:px-0 @4xl:order-3"
        >
          <Plus aria-hidden className="size-4" strokeWidth={2.5} />
          <span className="@max-xl:sr-only">{t("projects.new")}</span>
        </Link>
      </header>

      <section
        aria-label={t("projects.title")}
        className={`rounded-card border border-line bg-surface shadow-card ${
          rows.length > 0 && !projects.isPending && !projects.isError
            ? "@max-3xl:border-0 @max-3xl:bg-transparent"
            : ""
        }`}
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
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3 @3xl:block @3xl:divide-y @3xl:divide-line">
            {rows.map((project) => (
              <li key={project.id}>
                <Link
                  to={`/projects/${project.id}`}
                  className="glass-rim flex h-full flex-col gap-3 rounded-[18px] border border-line bg-surface p-4 shadow-[inset_0_1px_0_rgb(255_255_255/0.06)] transition-[background,transform] duration-200 hover:-translate-y-0.5 hover:bg-white/8 @3xl:grid @3xl:grid-cols-[minmax(10rem,1.2fr)_auto_auto_minmax(10rem,1.4fr)_auto_auto] @3xl:items-center @3xl:gap-4 @3xl:rounded-none @3xl:border-0 @3xl:bg-transparent @3xl:px-4 @3xl:py-3 @3xl:shadow-none @3xl:after:hidden @3xl:hover:translate-y-0 @3xl:hover:bg-bg"
                >
                  <span className="flex items-center gap-3 @3xl:contents">
                    <ProjectIcon name={project.name} />
                    <span className="min-w-0 flex-1 truncate font-medium @3xl:flex-none">
                      {project.name}
                    </span>
                    <span
                      className={`items-center gap-1 rounded-full text-sm @3xl:order-last @3xl:min-w-10 @3xl:bg-transparent @3xl:px-0 @3xl:text-fg ${
                        project.open_gates_count > 0
                          ? "flex bg-blocked/15 px-2 py-0.5 text-blocked"
                          : "hidden @3xl:flex"
                      }`}
                      aria-label={t("projects.openGates", { count: project.open_gates_count })}
                    >
                      {project.open_gates_count > 0 ? (
                        <>
                          <Bell aria-hidden className="size-4 text-blocked" />
                          {project.open_gates_count}
                        </>
                      ) : null}
                    </span>
                  </span>
                  <span className="flex flex-wrap items-center gap-2 @3xl:contents">
                    <ModeBadge mode={project.execution_mode} />
                    <StatusBadge status={project.status} />
                  </span>
                  <span className="truncate text-sm text-muted @3xl:text-fg">
                    <PhaseLine project={project} />
                  </span>
                  <span className="mt-auto border-t border-line pt-3 @3xl:mt-0 @3xl:border-0 @3xl:pt-0">
                    <BudgetBar spent={project.spent} budget={project.budget} compact />
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
