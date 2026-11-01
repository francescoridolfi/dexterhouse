// SPDX-License-Identifier: AGPL-3.0-or-later
// Shared gate panel (ux_2d_project_page.md): project page, inbox and, later, the 3D office.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "../../api/client.ts";
import { api } from "../../api/endpoints.ts";
import { keys, useMe } from "../../api/queries.ts";
import { ErrorState, LoadingBlock } from "../../components/Feedback.tsx";
import { Drawer } from "../../components/Overlay.tsx";
import { can } from "../../utils/auth.ts";
import { dateTime, relative } from "../../utils/format.ts";
import { ApprovalActions, ApprovalBody } from "./ApprovalBody.tsx";
import { EscalationActions, EscalationBody } from "./EscalationBody.tsx";
import { QuestionForm } from "./QuestionForm.tsx";
import { useDecide } from "./useDecide.ts";

const TYPE_TONE = {
  approval: "text-accent",
  question: "text-supervised",
  escalation: "text-failed",
};

export function GatePanel({ gateId, onClose }: { gateId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const me = useMe();
  const gate = useQuery({ queryKey: keys.gate(gateId), queryFn: () => api.gate(gateId) });
  const [next, setNext] = useState<string | null>(null);
  const decide = useDecide(gate.data, setNext);
  const data = gate.data;
  const admin = can(me.data, "admin");
  const decided = data && data.status !== "open";

  let body = null;
  let footer = null;
  if (data && !next) {
    if (data.type === "approval") {
      body = <ApprovalBody gate={data} />;
      footer = admin && !decided ? <ApprovalActions gate={data} decide={decide} /> : null;
    } else if (data.type === "question") {
      // Questions: member+ (E-06); approvals and escalations: admin.
      body = (
        <QuestionForm gate={data} decide={decide} disabled={!can(me.data, "member") || !!decided} />
      );
    } else {
      body = <EscalationBody gate={data} />;
      footer = admin && !decided ? <EscalationActions gate={data} decide={decide} /> : null;
    }
  }

  const problem = decide.error instanceof ApiError ? decide.error : null;

  return (
    <Drawer
      wide
      onClose={onClose}
      title={
        data ? (
          <span>
            <span
              className={`block text-xs font-bold tracking-wide uppercase ${TYPE_TONE[data.type]}`}
            >
              {t(`gate.type.${data.type}`)}
            </span>
            {data.payload.title}
          </span>
        ) : (
          t("gate.title")
        )
      }
      footer={
        <div className="space-y-2">
          {problem ? (
            <p role="alert" className="text-sm text-failed">
              {problem.status === 402 ? t("gate.budgetFirst") : problem.message}
            </p>
          ) : null}
          {!admin && data?.status === "open" && data.type !== "question" ? (
            <p className="text-sm text-muted">{t("gate.adminOnly")}</p>
          ) : null}
          {footer}
        </div>
      }
    >
      {gate.isPending ? (
        <LoadingBlock rows={5} />
      ) : gate.isError ? (
        <ErrorState error={gate.error} onRetry={() => void gate.refetch()} />
      ) : data ? (
        <div className="space-y-4">
          <p className="text-sm text-muted">
            {t("gate.openedAgo", { when: relative(data.opened_at) })}
            {data.expires_at ? ` · ${t("gate.expires", { when: dateTime(data.expires_at) })}` : ""}
          </p>
          <p className="text-sm whitespace-pre-wrap">{data.payload.summary}</p>
          {next ? (
            <p role="status" className="rounded-card border border-done bg-done/10 p-3 text-sm">
              {t(`gate.next.${next}`, { defaultValue: t("gate.next.default") })}
            </p>
          ) : decided ? (
            <p role="status" className="rounded-card border border-line p-3 text-sm">
              {t("gate.alreadyDecided", {
                who: data.decided_by?.name ?? t("events.system"),
                when: dateTime(data.decided_at),
                decision: data.decision ?? data.status,
              })}
            </p>
          ) : null}
          {body}
        </div>
      ) : null}
    </Drawer>
  );
}
