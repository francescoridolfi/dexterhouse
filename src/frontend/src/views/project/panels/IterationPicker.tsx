// SPDX-License-Identifier: AGPL-3.0-or-later
// Read-only selector of the project's iterations (brief = 0, CR-n = n) over the pipeline.
// TODO(E-13 task 16): the change-requests spec says Overview phases show past iterations,
// but the REST/snapshot contract does not expose phases per iteration yet (the snapshot
// only carries the current run). Until it does, picking a past iteration shows its CR
// summary instead of its phases. Wire `GET …/phases?iteration=n` (or equivalent) here.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ChangeRequest } from "../../../api/e13.ts";
import { StatusBadge } from "../../../components/Badges.tsx";
import { useProjectStore } from "../../../store/projectStore.ts";
import { dateTime, eur } from "../../../utils/format.ts";
import { useChangeRequests } from "../live.ts";

const STARTED = new Set(["running", "completed", "failed"]);

export function IterationPicker() {
  const { t } = useTranslation();
  const projectId = useProjectStore((s) => s.projectId ?? "");
  const crs = useChangeRequests(projectId);
  const started = (crs.data?.results ?? [])
    .filter((cr) => STARTED.has(cr.status) || cr.started_at)
    .sort((a, b) => a.number - b.number);
  const latest = started.at(-1)?.number ?? 0;
  const [picked, setPicked] = useState<number | null>(null);
  if (started.length === 0) return null;
  const value = picked ?? latest;
  const past: ChangeRequest | undefined =
    value === latest ? undefined : started.find((cr) => cr.number === value);
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 px-1 text-xs text-muted">
        {t("iterations.label")}
        <select
          value={value}
          onChange={(e) => setPicked(Number(e.target.value))}
          className="min-h-7 rounded-full border border-white/10 bg-black/25 px-2.5 text-xs text-fg"
        >
          <option value={0}>
            {t("iterations.brief")}
            {latest === 0 ? ` · ${t("iterations.current")}` : ""}
          </option>
          {started.map((cr) => (
            <option key={cr.id} value={cr.number}>
              CR-{cr.number}: {cr.title}
              {cr.number === latest ? ` · ${t("iterations.current")}` : ""}
            </option>
          ))}
        </select>
      </label>
      {value !== latest ? (
        <div role="note" className="os-pop rounded-[14px] bg-white/5 px-4 py-3 text-sm">
          {past ? (
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                CR-{past.number}: {past.title}
              </span>
              <StatusBadge status={past.status} label={t(`cr.status.${past.status}`)} />
              <span className="text-xs text-muted">
                {dateTime(past.started_at)} → {dateTime(past.completed_at)}
                {past.cost ? ` · ${eur(past.cost)}` : ""}
              </span>
            </p>
          ) : (
            <p className="font-medium">{t("iterations.brief")}</p>
          )}
          <p className="mt-1 text-xs text-muted">{t("iterations.readOnly")}</p>
        </div>
      ) : null}
    </div>
  );
}
