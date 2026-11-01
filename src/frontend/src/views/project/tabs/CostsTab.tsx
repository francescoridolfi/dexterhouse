// SPDX-License-Identifier: AGPL-3.0-or-later
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys, useMe } from "../../../api/queries.ts";
import { BudgetBar } from "../../../components/Badges.tsx";
import { Bars } from "../../../components/Bars.tsx";
import { Button } from "../../../components/Button.tsx";
import { Card, EmptyState, ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { can } from "../../../utils/auth.ts";
import { dateTime, eur, integer } from "../../../utils/format.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import { BudgetEditor } from "../ProjectHeader.tsx";

function CallsTable({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const calls = useInfiniteQuery({
    queryKey: keys.llmCalls(projectId),
    queryFn: ({ pageParam }) => api.llmCalls(projectId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next ?? undefined,
  });
  if (calls.isPending) return <LoadingBlock />;
  if (calls.isError) return <ErrorState error={calls.error} onRetry={() => void calls.refetch()} />;
  const rows = calls.data.pages.flatMap((p) => p.results);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-sm">
        <caption className="sr-only">{t("costs.calls")}</caption>
        <thead className="text-left text-xs text-muted uppercase">
          <tr>
            {["when", "model", "status", "tokens", "latency", "cost"].map((c) => (
              <th key={c} scope="col" className="px-3 py-2">
                {t(`costs.col.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((call) => (
            <tr key={call.id}>
              <td className="px-3 py-1.5">{dateTime(call.created_at)}</td>
              <td className="px-3 py-1.5 font-mono text-xs">
                {call.provider}/{call.model}
              </td>
              <td className={`px-3 py-1.5 ${call.status === "ok" ? "" : "text-failed"}`}>
                {call.status}
              </td>
              <td className="px-3 py-1.5">
                {integer(call.input_tokens)} / {integer(call.output_tokens)}
              </td>
              <td className="px-3 py-1.5">{call.latency_ms} ms</td>
              <td className="px-3 py-1.5">
                {call.cost === null ? t("costs.unpriced") : eur(call.cost)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {calls.hasNextPage ? (
        <div className="p-3 text-center">
          <Button busy={calls.isFetchingNextPage} onClick={() => void calls.fetchNextPage()}>
            {t("log.loadMore")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function CostsTab() {
  const { t } = useTranslation();
  const me = useMe();
  const projectId = useProjectStore((s) => s.projectId ?? "");
  const [editing, setEditing] = useState(false);
  const costs = useQuery({ queryKey: keys.costs(projectId), queryFn: () => api.costs(projectId) });
  if (costs.isPending) return <LoadingBlock rows={6} />;
  if (costs.isError) return <ErrorState error={costs.error} onRetry={() => void costs.refetch()} />;
  const c = costs.data;
  const estimate = t("costs.estimate", {
    low: eur(c.estimate.low, 0),
    high: eur(c.estimate.high, 0),
  });
  if (c.by_provider.length === 0) {
    return <EmptyState title={t("costs.empty", { estimate })} />;
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title={t("costs.total")} className="lg:col-span-2">
        <div className="flex flex-wrap items-center gap-4 p-4">
          <BudgetBar spent={c.spent} budget={c.budget} />
          <span className="text-sm text-muted">
            {estimate} · {t(`estimate.${c.estimate.basis}`)}
          </span>
          {c.unpriced_tokens > 0 ? (
            <span className="text-sm text-blocked">
              {t("costs.unpricedTokens", { n: integer(c.unpriced_tokens) })}
            </span>
          ) : null}
          {can(me.data, "member") ? (
            editing ? (
              <BudgetEditor onDone={() => setEditing(false)} />
            ) : (
              <Button size="sm" onClick={() => setEditing(true)}>
                {t("budget.edit")}
              </Button>
            )
          ) : null}
        </div>
      </Card>
      <Card title={t("costs.byPhase")}>
        <div className="p-4">
          <Bars
            label={t("costs.byPhase")}
            bars={c.by_phase.map((p) => ({
              key: p.phase_run ?? "none",
              label: p.phase_id
                ? t(`phase.${p.phase_id}`, { defaultValue: p.phase_id })
                : t("costs.unattributed"),
              value: Number(p.cost),
              display: eur(p.cost),
            }))}
          />
        </div>
      </Card>
      <Card title={t("costs.byDay")}>
        <div className="p-4">
          <Bars
            label={t("costs.byDay")}
            bars={c.by_day.map((d) => ({
              key: d.day,
              label: d.day,
              value: Number(d.cost),
              display: eur(d.cost),
            }))}
          />
        </div>
      </Card>
      <Card title={t("costs.byAgent")}>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted uppercase">
            <tr>
              <th scope="col" className="px-3 py-2">
                {t("costs.col.agent")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("costs.col.turns")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("costs.col.tokens")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("costs.col.cost")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {c.by_agent.map((a) => (
              <tr key={a.agent_id ?? "none"}>
                <td className="px-3 py-1.5">{a.display_name ?? t("costs.unattributed")}</td>
                <td className="px-3 py-1.5">{a.turns}</td>
                <td className="px-3 py-1.5">{integer(a.input_tokens + a.output_tokens)}</td>
                <td className="px-3 py-1.5">{eur(a.cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title={t("costs.byProvider")}>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted uppercase">
            <tr>
              <th scope="col" className="px-3 py-2">
                {t("costs.col.model")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("costs.col.calls")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("costs.col.latency")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("costs.col.cost")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {c.by_provider.map((p) => (
              <tr key={`${p.provider}/${p.model}`}>
                <td className="px-3 py-1.5 font-mono text-xs">
                  {p.provider}/{p.model}
                </td>
                <td className="px-3 py-1.5">
                  {p.calls}
                  {p.errors ? (
                    <span className="text-failed"> ({t("costs.errors", { n: p.errors })})</span>
                  ) : null}
                </td>
                <td className="px-3 py-1.5">
                  {p.avg_latency_ms !== null ? `${p.avg_latency_ms} ms` : "—"}
                </td>
                <td className="px-3 py-1.5">{eur(p.cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title={t("costs.calls")} className="lg:col-span-2">
        <CallsTable projectId={projectId} />
      </Card>
    </div>
  );
}
