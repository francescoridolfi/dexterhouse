// SPDX-License-Identifier: AGPL-3.0-or-later
import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys } from "../../../api/queries.ts";
import type { EventEnvelope } from "../../../api/types.ts";
import { Button } from "../../../components/Button.tsx";
import { Card, EmptyState, ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
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
  const select = "min-h-11 rounded-card border border-line bg-surface px-2 text-sm";

  return (
    <Card title={t("log.timeline")}>
      <div className="flex flex-wrap gap-2 border-b border-line p-3">
        <select
          aria-label={t("log.filterType")}
          value={filters.family}
          onChange={(e) => set("family")(e.target.value)}
          className={select}
        >
          <option value="">{t("log.allTypes")}</option>
          {FAMILIES.map((f) => (
            <option key={f} value={f}>
              {f}.*
            </option>
          ))}
        </select>
        <select
          aria-label={t("log.filterAgent")}
          value={filters.agent}
          onChange={(e) => set("agent")(e.target.value)}
          className={select}
        >
          <option value="">{t("log.allAgents")}</option>
          {Object.values(agents).map((a) => (
            <option key={a.id} value={a.id}>
              {a.displayName}
            </option>
          ))}
        </select>
        <select
          aria-label={t("log.filterPhase")}
          value={filters.phase}
          onChange={(e) => set("phase")(e.target.value)}
          className={select}
        >
          <option value="">{t("log.allPhases")}</option>
          {phases.map((p) => (
            <option key={p} value={p}>
              {t(`phase.${p}`, { defaultValue: p })}
            </option>
          ))}
        </select>
        <input
          type="search"
          aria-label={t("log.filterText")}
          placeholder={t("log.filterText")}
          value={filters.text}
          onChange={(e) => set("text")(e.target.value)}
          className={`${select} flex-1`}
        />
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
                  <summary className="grid cursor-pointer grid-cols-[9rem_8rem_1.25rem_1fr] gap-2 px-3 py-1.5 hover:bg-bg max-md:grid-cols-[1.25rem_1fr]">
                    <time dateTime={event.created_at} className="text-muted max-md:hidden">
                      {dateTime(event.created_at)}
                    </time>
                    <span className="truncate max-md:hidden">{actorLabel(event, agents, t)}</span>
                    <span aria-hidden>{line.icon}</span>
                    <span className={TONE_CLASS[line.tone]}>
                      <span className="text-muted">{event.type}</span> {line.text}
                    </span>
                  </summary>
                  <div className="space-y-2 bg-bg px-3 py-2">
                    <pre className="overflow-auto whitespace-pre-wrap">
                      {JSON.stringify(event.payload, null, 2)}
                    </pre>
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
