// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys } from "../../../api/queries.ts";
import { ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { Drawer } from "../../../components/Overlay.tsx";
import { duration, eur, integer } from "../../../utils/format.ts";

/** "What the agent knew" (context manifest), costs and every tool call of one turn. */
export function TurnDrawer({ turnId, onClose }: { turnId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const turn = useQuery({ queryKey: keys.turn(turnId), queryFn: () => api.turn(turnId) });
  const data = turn.data;
  return (
    <Drawer title={data?.purpose ?? t("turn.title")} onClose={onClose} wide>
      {turn.isPending ? (
        <LoadingBlock />
      ) : turn.isError ? (
        <ErrorState error={turn.error} onRetry={() => void turn.refetch()} />
      ) : data ? (
        <div className="space-y-4 text-sm">
          <dl className="grid grid-cols-2 gap-1">
            <dt className="text-muted">{t("turn.status")}</dt>
            <dd>
              {data.status}
              {data.error_code ? ` (${data.error_code})` : ""}
            </dd>
            <dt className="text-muted">{t("turn.cost")}</dt>
            <dd>{eur(data.cost)}</dd>
            <dt className="text-muted">{t("turn.tokens")}</dt>
            <dd>
              {integer(data.input_tokens)} / {integer(data.output_tokens)} (
              {t("turn.cached", { n: integer(data.cached_tokens) })})
            </dd>
            <dt className="text-muted">{t("turn.duration")}</dt>
            <dd>
              {data.started_at && data.finished_at
                ? duration((Date.parse(data.finished_at) - Date.parse(data.started_at)) / 1000)
                : "—"}
            </dd>
            <dt className="text-muted">{t("turn.profile")}</dt>
            <dd>{data.profile_used || "—"}</dd>
          </dl>
          <details open>
            <summary className="cursor-pointer font-semibold">{t("turn.manifest")}</summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-card bg-bg p-2 font-mono text-xs">
              {JSON.stringify(data.context_manifest ?? {}, null, 2)}
            </pre>
          </details>
          <section>
            <h3 className="font-semibold">
              {t("turn.toolCalls", { count: data.tool_calls?.length ?? 0 })}
            </h3>
            <ol className="mt-2 space-y-2">
              {(data.tool_calls ?? []).map((call) => (
                <li key={call.seq}>
                  <details className="rounded-card border border-line">
                    <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 font-mono text-xs">
                      <span className={call.allowed ? "" : "text-failed"}>
                        {call.allowed ? "⚙" : "⛔"}
                      </span>
                      {call.seq}. {call.tool}
                      <span className="ml-auto text-muted">
                        {call.duration_ms} ms · {call.status}
                      </span>
                    </summary>
                    <div className="space-y-2 border-t border-line p-3">
                      <p className="text-xs font-semibold">{t("turn.arguments")}</p>
                      <pre className="overflow-auto rounded bg-bg p-2 font-mono text-xs">
                        {JSON.stringify(call.arguments, null, 2)}
                      </pre>
                      <p className="text-xs font-semibold">{t("turn.result")}</p>
                      <pre className="max-h-48 overflow-auto rounded bg-bg p-2 font-mono text-xs whitespace-pre-wrap">
                        {call.denied_reason ?? call.result_excerpt ?? "—"}
                        {call.truncated ? `\n… ${t("turn.truncated")}` : ""}
                      </pre>
                    </div>
                  </details>
                </li>
              ))}
            </ol>
          </section>
        </div>
      ) : null}
    </Drawer>
  );
}
