// SPDX-License-Identifier: AGPL-3.0-or-later
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusDot } from "../../../components/Badges.tsx";
import { Card, EmptyState } from "../../../components/Feedback.tsx";
import { duration, eur } from "../../../utils/format.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import { openGates, orderedPhases, phaseProgress } from "../../../store/selectors.ts";
import type { PhaseView } from "../../../store/model.ts";

function liveDuration(phase: PhaseView): number | null {
  if (phase.durationS !== null) return phase.durationS;
  if (!phase.startedAt) return null;
  return (Date.now() - Date.parse(phase.startedAt)) / 1000;
}

export function Pipeline({ onOpenGate }: { onOpenGate: (id: string) => void }) {
  const { t } = useTranslation();
  const state = useProjectStore();
  const phases = orderedPhases(state);
  const gates = openGates(state);
  const [selected, setSelected] = useState<string | null>(null);
  const detail = phases.find((p) => p.phaseId === selected);

  return (
    <Card title={t("pipeline.title")}>
      {phases.length === 0 ? (
        <EmptyState title={t("pipeline.empty")} />
      ) : (
        <ol className="flex gap-2 overflow-x-auto p-4" aria-label={t("pipeline.title")}>
          {phases.map((phase, index) => {
            const progress = phaseProgress(state, phase);
            const time = liveDuration(phase);
            return (
              <li key={phase.phaseId} className="flex shrink-0 items-center gap-2">
                {index > 0 ? <span aria-hidden className="h-px w-4 bg-line" /> : null}
                <button
                  type="button"
                  onClick={() => setSelected(selected === phase.phaseId ? null : phase.phaseId)}
                  aria-expanded={selected === phase.phaseId}
                  className={`min-h-11 rounded-card border px-3 py-1.5 text-left ${phase.status === "running" || phase.status === "waiting_gate" ? "border-accent" : "border-line"}`}
                >
                  <span className="flex items-center gap-1.5 text-sm font-medium">
                    <StatusDot status={phase.status} />
                    {t(`phase.${phase.phaseId}`, { defaultValue: phase.phaseId })}
                    {progress ? (
                      <span className="text-muted">
                        ({progress.done}/{progress.total})
                      </span>
                    ) : null}
                  </span>
                  <span className="block text-xs text-muted">
                    {t(`phaseStatus.${phase.status}`)} {time !== null ? `· ${duration(time)}` : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
      {detail ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-line p-4 text-sm @3xl:grid-cols-4">
          <dt className="text-muted">{t("pipeline.status")}</dt>
          <dd>{t(`phaseStatus.${detail.status}`)}</dd>
          <dt className="text-muted">{t("pipeline.room")}</dt>
          <dd>{t(`room.${detail.room}`, { defaultValue: detail.room || "—" })}</dd>
          <dt className="text-muted">{t("pipeline.duration")}</dt>
          <dd>{duration(liveDuration(detail)) || "—"}</dd>
          <dt className="text-muted">{t("pipeline.cost")}</dt>
          <dd>{detail.cost !== null ? eur(detail.cost) : "—"}</dd>
          <dt className="text-muted">{t("pipeline.step")}</dt>
          <dd>{detail.currentStep}</dd>
          <dt className="text-muted">{t("pipeline.round")}</dt>
          <dd>{detail.round}</dd>
          {gates
            .filter((g) => g.phaseId === detail.phaseId)
            .map((g) => (
              <dd key={g.id} className="col-span-2">
                <button
                  type="button"
                  className="text-accent underline"
                  onClick={() => onOpenGate(g.id)}
                >
                  {g.title}
                </button>
              </dd>
            ))}
        </dl>
      ) : null}
    </Card>
  );
}
