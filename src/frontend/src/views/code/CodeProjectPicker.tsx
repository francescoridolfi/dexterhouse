// SPDX-License-Identifier: AGPL-3.0-or-later
// `/code` (the dock tile with no Code window open): pick the project whose code to open.
import { ChevronRight, CodeXml } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useProjects } from "../../api/queries.ts";
import { StatusDot } from "../../components/Badges.tsx";
import { EmptyState, ErrorState, LoadingBlock } from "../../components/Feedback.tsx";
import { codeHref } from "./links.ts";

export function CodeProjectPicker() {
  const { t } = useTranslation();
  const projects = useProjects({});
  return (
    <div className="mx-auto max-w-xl space-y-3 pt-2">
      <h1 className="text-[22px] font-semibold tracking-tight">{t("codeApp.pickProject")}</h1>
      {projects.isPending ? (
        <LoadingBlock />
      ) : projects.isError ? (
        <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
      ) : projects.data.results.length === 0 ? (
        <EmptyState
          icon={<CodeXml aria-hidden className="size-8" />}
          title={t("codeApp.noProjects")}
        />
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface">
          {projects.data.results.map((p) => (
            <li key={p.id}>
              <Link
                to={codeHref(p.id)}
                className="flex min-h-11 items-center gap-3 px-4 hover:bg-white/6"
              >
                <StatusDot status={p.status} className="size-2" />
                <span className="min-w-0 flex-1 truncate font-medium">{p.name}</span>
                <ChevronRight aria-hidden className="size-4 text-muted" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
