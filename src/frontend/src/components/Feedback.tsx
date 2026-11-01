// SPDX-License-Identifier: AGPL-3.0-or-later
// Loading, empty and error states used everywhere (ux_2d_states.md).
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { errorMessage } from "../utils/errors.ts";

export function Spinner({ label }: { label?: string }) {
  return <Loader2 aria-hidden={!label} aria-label={label} className="size-4 animate-spin" />;
}

export function Skeleton({
  className = "h-4 w-full",
  count = 1,
}: {
  className?: string;
  count?: number;
}) {
  return (
    <div aria-hidden="true" className="space-y-2">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className={`animate-pulse rounded bg-line ${className}`} />
      ))}
    </div>
  );
}

export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  const { t } = useTranslation();
  return (
    <div role="status" aria-label={t("loading")} className="p-4">
      <Skeleton count={rows} className="h-6 w-full" />
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
      <span className="text-muted">{icon ?? <Inbox aria-hidden className="size-8" />}</span>
      <p className="max-w-md text-fg">{title}</p>
      {children ? <div className="max-w-md text-sm text-muted">{children}</div> : null}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="flex flex-col items-center gap-3 px-4 py-10 text-center">
      <AlertTriangle aria-hidden className="size-8 text-failed" />
      <p className="font-medium">{t("error.title")}</p>
      <p className="max-w-md text-sm text-muted">{errorMessage(error, t("error.unknown"))}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="min-h-11 rounded-card px-4 text-accent underline"
        >
          {t("retry")}
        </button>
      ) : null}
    </div>
  );
}

export function Card({
  title,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-card border border-line bg-surface shadow-card ${className}`}>
      {title || actions ? (
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h2 className="text-xs font-semibold tracking-wide text-muted uppercase">{title}</h2>
          {actions}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function ComingSoon({ title, children }: { title: string; children?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-card border border-dashed border-line bg-surface p-6 text-center">
      <span className="inline-block rounded-full bg-bg px-3 py-1 text-xs font-semibold tracking-wide text-muted uppercase">
        {t("comingSoon")}
      </span>
      <p className="mt-3 font-medium">{title}</p>
      {children ? <div className="mt-2 text-sm text-muted">{children}</div> : null}
    </div>
  );
}
