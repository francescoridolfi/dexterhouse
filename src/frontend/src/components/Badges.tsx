// SPDX-License-Identifier: AGPL-3.0-or-later
// Status, mode and budget indicators: same token = same colour in 2D and 3D (theme.md).
import { useTranslation } from "react-i18next";

import type { ExecutionMode } from "../api/types.ts";
import { eur } from "../utils/format.ts";
import { budgetLevel } from "../store/selectors.ts";

const TONE: Record<string, string> = {
  idle: "bg-idle",
  working: "bg-working",
  running: "bg-working",
  ready: "bg-working",
  blocked: "bg-blocked",
  waiting: "bg-blocked",
  waiting_gate: "bg-blocked",
  reopened: "bg-blocked",
  paused: "bg-idle",
  failed: "bg-failed",
  escalated: "bg-failed",
  done: "bg-done",
  completed: "bg-done",
  skipped: "bg-idle",
  draft: "bg-idle",
  archived: "bg-idle",
  open: "bg-blocked",
};

export function StatusDot({ status, className = "" }: { status: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block size-2.5 shrink-0 rounded-full ${TONE[status] ?? "bg-idle"} ${className}`}
    />
  );
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs font-medium">
      <StatusDot status={status} />
      {label ?? t(`status.${status}`, { defaultValue: status })}
    </span>
  );
}

export function ModeBadge({ mode, onClick }: { mode: ExecutionMode; onClick?: () => void }) {
  const { t } = useTranslation();
  const color =
    mode === "supervised"
      ? "border-supervised text-supervised"
      : "border-autonomous text-autonomous";
  const content = t(`mode.${mode}`).toUpperCase();
  const classes = `inline-flex min-h-7 items-center rounded-full border-2 px-2.5 text-xs font-bold tracking-wider ${color}`;
  if (!onClick) return <span className={classes}>{content}</span>;
  return (
    <button
      type="button"
      onClick={onClick}
      className={classes}
      aria-label={t("mode.explain", { mode: content })}
    >
      {content}
    </button>
  );
}

export function BudgetBar({
  spent,
  budget,
  compact = false,
}: {
  spent: number | string;
  budget: number | string;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const s = Number(spent);
  const b = Number(budget);
  const level = budgetLevel(s, b);
  const pct = b > 0 ? Math.min(100, (s / b) * 100) : s > 0 ? 100 : 0;
  const fill = { ok: "bg-budget-ok", warn: "bg-budget-warn", over: "bg-budget-over" }[level];
  return (
    <div className={`flex items-center gap-2 ${compact ? "min-w-36" : "min-w-48"}`}>
      <div
        role="meter"
        aria-label={t("budget.meter")}
        aria-valuemin={0}
        aria-valuemax={b}
        aria-valuenow={s}
        aria-valuetext={t("budget.of", { spent: eur(s), budget: eur(b) })}
        className="h-2 flex-1 overflow-hidden rounded-full bg-line"
      >
        <div
          className={`h-full ${fill} transition-[width] duration-400`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`shrink-0 font-mono text-xs ${level === "over" ? "text-failed" : ""}`}>
        {eur(s)} / {eur(b, 0)}
      </span>
    </div>
  );
}
