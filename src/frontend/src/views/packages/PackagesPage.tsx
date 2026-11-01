// SPDX-License-Identifier: AGPL-3.0-or-later
// The packages API (E-07) and the marketplace proxy (E-11) do not exist yet: this page lists
// what `GET /meta` knows (built-in processes) and says what is coming.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useMeta } from "../../api/queries.ts";
import { Card, ComingSoon, ErrorState, LoadingBlock } from "../../components/Feedback.tsx";

export function PackagesPage() {
  const { t } = useTranslation();
  const meta = useMeta();
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-2xl font-semibold">{t("packages.title")}</h1>
        <Link
          to="/packages/marketplace"
          className="inline-flex min-h-11 items-center rounded-card border border-line px-4 text-sm"
        >
          {t("packages.marketplace")}
        </Link>
      </div>
      <Card title={t("packages.builtinProcesses")}>
        {meta.isPending ? (
          <LoadingBlock />
        ) : meta.isError ? (
          <ErrorState error={meta.error} onRetry={() => void meta.refetch()} />
        ) : (
          <ul className="divide-y divide-line">
            {meta.data.processes.map((p) => (
              <li key={p.name} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <span aria-hidden>🗺</span>
                <span className="font-mono font-medium">{p.name}</span>
                <span className="text-muted">{t("source.builtin")}</span>
                <span className="font-mono">{p.version}</span>
                <span className="text-muted">{t("packages.kind.process")}</span>
                <span className="ml-auto text-xs text-muted">
                  {p.phases.map((ph) => ph.id).join(" → ")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <ComingSoon title={t("packages.installedSoon")}>
        {t("packages.installedSoonDetail")}
      </ComingSoon>
    </div>
  );
}

export function MarketplacePage() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center gap-3">
        <Link to="/packages" className="text-sm text-muted hover:text-fg">
          ← {t("packages.title")}
        </Link>
        <h1 className="text-2xl font-semibold">{t("packages.marketplace")}</h1>
      </div>
      <div aria-disabled="true" className="flex flex-wrap gap-2 opacity-60">
        <input
          disabled
          aria-label={t("packages.search")}
          placeholder={t("packages.search")}
          className="min-h-11 flex-1 rounded-card border border-line bg-surface px-3"
        />
        <select
          disabled
          aria-label={t("packages.kindFilter")}
          className="min-h-11 rounded-card border border-line bg-surface px-2"
        >
          <option>{t("packages.allKinds")}</option>
        </select>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" disabled /> {t("packages.verifiedOnly")}
        </label>
      </div>
      <ComingSoon title={t("packages.marketplaceSoon")}>
        {t("packages.marketplaceSoonDetail")}
      </ComingSoon>
    </div>
  );
}
