// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useOpenGates, useProjects } from "../../api/queries.ts";
import { EmptyState, ErrorState, LoadingBlock } from "../../components/Feedback.tsx";
import { relative } from "../../utils/format.ts";
import { GatePanel } from "../gates/GatePanel.tsx";

const ICON = { escalation: "⚠", question: "❓", approval: "✋" };
const RANK = { escalation: 0, question: 1, approval: 2 };

export function InboxPage() {
  const { t } = useTranslation();
  const gates = useOpenGates();
  const projects = useProjects({});
  const [type, setType] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const names = useMemo(
    () => new Map((projects.data?.results ?? []).map((p) => [p.id, p.name])),
    [projects.data],
  );
  const rows = (gates.data?.results ?? [])
    .filter((g) => !type || g.type === type)
    .sort((a, b) => RANK[a.type] - RANK[b.type] || a.opened_at.localeCompare(b.opened_at));

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-2xl font-semibold">
          {t("inbox.title", { count: gates.data?.results.length ?? 0 })}
        </h1>
        <label htmlFor="inbox-type" className="sr-only">
          {t("inbox.filter")}
        </label>
        <select
          id="inbox-type"
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="min-h-11 rounded-card border border-line bg-surface px-2 text-sm"
        >
          <option value="">{t("inbox.all")}</option>
          {(["escalation", "question", "approval"] as const).map((g) => (
            <option key={g} value={g}>
              {t(`gate.type.${g}`)}
            </option>
          ))}
        </select>
      </div>
      <section className="rounded-card border border-line bg-surface shadow-card">
        {gates.isPending ? (
          <LoadingBlock rows={3} />
        ) : gates.isError ? (
          <ErrorState error={gates.error} onRetry={() => void gates.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            title={t("inbox.empty")}
            action={
              <Link to="/projects" className="text-accent underline">
                {t("inbox.toProjects")}
              </Link>
            }
          />
        ) : (
          <ul className="divide-y divide-line">
            {rows.map((gate) => (
              <li key={gate.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <span aria-hidden>{ICON[gate.type]}</span>
                <span className="w-28 text-xs font-bold tracking-wide uppercase">
                  {t(`gate.type.${gate.type}`)}
                </span>
                <span className="min-w-48 flex-1 text-sm">
                  <Link to={`/projects/${gate.project}`} className="font-medium hover:underline">
                    {names.get(gate.project) ?? t("inbox.project")}
                  </Link>{" "}
                  · {gate.payload.title}
                </span>
                <span className="text-xs text-muted">{relative(gate.opened_at)}</span>
                <button
                  type="button"
                  onClick={() => setOpen(gate.id)}
                  className="min-h-11 rounded-card border border-line px-4 text-sm font-medium hover:border-accent"
                >
                  {t(`inbox.action.${gate.type}`)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      {open ? <GatePanel gateId={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}
