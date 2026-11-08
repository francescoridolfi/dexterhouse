// SPDX-License-Identifier: AGPL-3.0-or-later
import { useInfiniteQuery } from "@tanstack/react-query";
import { Bot, Layers, Tags } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../../../api/endpoints.ts";
import { keys } from "../../../api/queries.ts";
import type { EventEnvelope } from "../../../api/types.ts";
import { Button } from "../../../components/Button.tsx";
import { Card, EmptyState, ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import {
  FilterBar,
  FilterGroup,
  FilterSelect,
  SearchField,
} from "../../../components/FilterBar.tsx";
import { TONE_CLASS, actorLabel, describeEvent } from "../../../utils/events.ts";
import { dateTime } from "../../../utils/format.ts";
import { type LogFilters, filterEvents } from "../../../utils/logFilter.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import { TurnDrawer } from "../panels/TurnDrawer.tsx";

const FAMILIES = [
  "project",
  "phase",
  "agent",
  "task",
  "gate",
  "note",
  "budget",
  "test",
  "security",
  "release",
];

export function LogTab() {
  const { t } = useTranslation();
  const projectId = useProjectStore((s) => s.projectId ?? "");
  const live = useProjectStore((s) => s.events);
  const agents = useProjectStore((s) => s.agents);
  const tasks = useProjectStore((s) => s.tasks);
  const phases = useProjectStore((s) => s.phaseOrder);
  const [filters, setFilters] = useState<LogFilters>({
    family: "",
    agent: "",
    phase: "",
    text: "",
  });
  const [turn, setTurn] = useState<string | null>(null);
  const history = useInfiniteQuery({
    queryKey: keys.events(projectId, {}),
    queryFn: ({ pageParam }) => api.events(projectId, {}, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next ?? undefined,
    staleTime: Infinity,
  });
  const merged = useMemo(() => {
    const byId = new Map<string, EventEnvelope>();
    for (const page of history.data?.pages ?? []) for (const e of page.results) byId.set(e.id, e);
    for (const e of live) byId.set(e.id, e);
    return [...byId.values()].sort(
      (a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id),
    );
  }, [history.data, live]);
  const rows = filterEvents(merged, filters, (e) => describeEvent(e, t, tasks).text).reverse();
  const set = (key: keyof LogFilters) => (value: string) =>
    setFilters((f) => ({ ...f, [key]: value }));

  return (
    <Card title={t("log.timeline")}>
      <div className="border-b border-line p-3">
        <FilterBar>
          <SearchField label={t("log.filterText")} value={filters.text} onChange={set("text")} />
          <FilterGroup>
            <FilterSelect
              id="log-filter-type"
              label={t("log.filterType")}
              icon={<Tags aria-hidden className="size-3.5" />}
              value={filters.family}
              onChange={set("family")}
              options={[
                ["", t("log.allTypes")],
                ...FAMILIES.map((f): [string, string] => [f, `${f}.*`]),
              ]}
            />
            <FilterSelect
              id="log-filter-agent"
              label={t("log.filterAgent")}
              icon={<Bot aria-hidden className="size-3.5" />}
              value={filters.agent}
              onChange={set("agent")}
              options={[
                ["", t("log.allAgents")],
                ...Object.values(agents).map((a): [string, string] => [a.id, a.displayName]),
              ]}
            />
            <FilterSelect
              id="log-filter-phase"
              label={t("log.filterPhase")}
              icon={<Layers aria-hidden className="size-3.5" />}
              value={filters.phase}
              onChange={set("phase")}
              options={[
                ["", t("log.allPhases")],
                ...phases.map((p): [string, string] => [p, t(`phase.${p}`, { defaultValue: p })]),
              ]}
            />
          </FilterGroup>
        </FilterBar>
      </div>
      {history.isPending ? (
        <LoadingBlock rows={6} />
      ) : history.isError ? (
        <ErrorState error={history.error} onRetry={() => void history.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title={t("log.noEvents")} />
      ) : (
        <ol className="divide-y divide-line font-mono text-xs">
          {rows.map((event) => {
            const line = describeEvent(event, t, tasks);
            const turnId = typeof event.payload.turn_id === "string" ? event.payload.turn_id : null;
            return (
              <li key={event.id}>
                <details>
                  <summary className="grid cursor-pointer grid-cols-[9rem_8rem_1.25rem_1fr] gap-2 px-3 py-1.5 hover:bg-bg @max-3xl:grid-cols-[1.25rem_1fr]">
                    <time dateTime={event.created_at} className="text-muted @max-3xl:hidden">
                      {dateTime(event.created_at)}
                    </time>
                    <span className="truncate @max-3xl:hidden">{actorLabel(event, agents, t)}</span>
                    <span aria-hidden>{line.icon}</span>
                    <span className={TONE_CLASS[line.tone]}>
                      <span className="text-muted">{event.type}</span> {line.text}
                    </span>
                  </summary>
                  <div className="space-y-2 bg-bg px-3 py-2">
                    <pre className="overflow-auto whitespace-pre-wrap">
                      {JSON.stringify(event.payload, null, 2)}
                    </pre>
                    <Link
                      to={`/projects/${projectId}/office?replay=${encodeURIComponent(event.created_at)}`}
                      className="mr-3 text-accent underline"
                    >
                      {t("log.replay")}
                    </Link>
                    {turnId && event.type.startsWith("agent.turn.") ? (
                      <button
                        type="button"
                        className="text-accent underline"
                        onClick={() => setTurn(turnId)}
                      >
                        {t("log.openTurn")}
                      </button>
                    ) : null}
                  </div>
                </details>
              </li>
            );
          })}
        </ol>
      )}
      {history.hasNextPage ? (
        <div className="p-3 text-center">
          <Button busy={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>
            {t("log.loadMore")}
          </Button>
        </div>
      ) : null}
      {turn ? <TurnDrawer turnId={turn} onClose={() => setTurn(null)} /> : null}
    </Card>
  );
}
