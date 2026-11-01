// SPDX-License-Identifier: AGPL-3.0-or-later
import type { UseMutationResult } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { DecideBody } from "../../api/endpoints.ts";
import type { Gate } from "../../api/types.ts";
import { Button } from "../../components/Button.tsx";
import { ConfirmDialog } from "../../components/Overlay.tsx";
import { useProjectStore } from "../../store/projectStore.ts";
import { BudgetEditor } from "../project/ProjectHeader.tsx";
import { isBudgetGate } from "./budget.ts";

type Decide = UseMutationResult<Gate, Error, DecideBody>;

export function EscalationBody({ gate }: { gate: Gate }) {
  const { t } = useTranslation();
  const inProject = useProjectStore((s) => s.projectId === gate.project);
  const attempts = gate.payload.attempts ?? [];
  if (isBudgetGate(gate)) {
    return (
      <div className="space-y-3 text-sm">
        <p>{t("gate.budgetExplain")}</p>
        {inProject ? (
          <BudgetEditor onDone={() => undefined} />
        ) : (
          <p className="text-muted">{t("gate.budgetOpenProject")}</p>
        )}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-sm">
        {t(`gate.reason.${gate.payload.reason ?? "default"}`, {
          defaultValue: gate.payload.reason ?? "",
        })}
      </p>
      {attempts.length ? (
        <table className="w-full text-sm">
          <caption className="sr-only">{t("gate.attempts")}</caption>
          <thead className="text-left text-xs text-muted uppercase">
            <tr>
              <th scope="col" className="py-1">
                {t("gate.iteration")}
              </th>
              <th scope="col" className="py-1">
                {t("gate.step")}
              </th>
              <th scope="col" className="py-1">
                {t("gate.verdict")}
              </th>
              <th scope="col" className="py-1">
                {t("gate.summary")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {attempts.map((a, i) => (
              <tr key={i}>
                <td className="py-1">{a.iteration ?? "—"}</td>
                <td className="py-1">{a.step ?? "—"}</td>
                <td
                  className={`py-1 ${a.verdict === "fail" || a.verdict === "request_changes" ? "text-failed" : ""}`}
                >
                  {a.verdict ?? "—"}
                </td>
                <td className="py-1">{a.summary ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

/** Flow F8 (and F7 for the budget gate): retry with a note, accept as is, drop. */
export function EscalationActions({ gate, decide }: { gate: Gate; decide: Decide }) {
  const { t } = useTranslation();
  const [note, setNote] = useState("");
  const [confirm, setConfirm] = useState<"accept" | "drop" | null>(null);
  const budget = isBudgetGate(gate);
  return (
    <div className="space-y-2">
      {!budget ? (
        <>
          <label htmlFor="escalation-note" className="text-sm font-medium">
            {t("gate.retryNote")}
          </label>
          <textarea
            id="escalation-note"
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full rounded-card border border-line bg-bg p-2 text-sm"
          />
        </>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="danger" onClick={() => setConfirm("drop")}>
          {t(budget ? "gate.dropProject" : "gate.drop")}
        </Button>
        {!budget ? <Button onClick={() => setConfirm("accept")}>{t("gate.accept")}</Button> : null}
        <Button
          variant="primary"
          busy={decide.isPending}
          onClick={() => decide.mutate({ decision: "retry", comment: note || undefined })}
        >
          {t(budget ? "gate.resumeBudget" : "gate.retry")}
        </Button>
      </div>
      {confirm ? (
        <ConfirmDialog
          title={t(
            confirm === "drop" ? (budget ? "gate.dropProject" : "gate.drop") : "gate.accept",
          )}
          message={t(
            confirm === "drop"
              ? budget
                ? "gate.dropProjectMessage"
                : "gate.dropMessage"
              : "gate.acceptMessage",
          )}
          confirmLabel={t("confirm")}
          danger={confirm === "drop"}
          busy={decide.isPending}
          onConfirm={() => {
            decide.mutate({ decision: confirm, comment: note || undefined });
            setConfirm(null);
          }}
          onCancel={() => setConfirm(null)}
        />
      ) : null}
    </div>
  );
}
