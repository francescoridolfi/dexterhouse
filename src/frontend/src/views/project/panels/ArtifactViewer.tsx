// SPDX-License-Identifier: AGPL-3.0-or-later
// Artifact viewer with version diff (Artifacts tab, 3D documents and test report).
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys } from "../../../api/queries.ts";
import type { Artifact } from "../../../api/types.ts";
import { ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { dateTime } from "../../../utils/format.ts";
import { ArtifactContent, DiffView } from "../../shared/DiffView.tsx";

function downloadHref(artifact: Artifact): string {
  const body = artifact.content || JSON.stringify(artifact.data ?? {}, null, 2);
  return URL.createObjectURL(new Blob([body], { type: "text/plain;charset=utf-8" }));
}

export function ArtifactViewer({ artifactId }: { artifactId: string }) {
  const { t } = useTranslation();
  const artifact = useQuery({
    queryKey: keys.artifact(artifactId),
    queryFn: () => api.artifact(artifactId),
  });
  const versions = useQuery({
    queryKey: keys.versions(artifactId),
    queryFn: () => api.artifactVersions(artifactId),
  });
  const [against, setAgainst] = useState<number | null>(null);
  const diff = useQuery({
    queryKey: keys.diff(artifactId, against ?? 0),
    queryFn: () => api.artifactDiff(artifactId, against ?? 0),
    enabled: against !== null,
  });
  if (artifact.isPending) return <LoadingBlock />;
  if (artifact.isError)
    return <ErrorState error={artifact.error} onRetry={() => void artifact.refetch()} />;
  const a = artifact.data;
  const older = (versions.data?.results ?? []).filter((v) => v.version < a.version);
  return (
    <div className="space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-mono text-sm font-semibold">
          {a.name} v{a.version}
        </h3>
        <span className="text-xs text-muted">
          {t("artifacts.producedBy", {
            role: a.produced_by.role ?? t("artifacts.user"),
            date: dateTime(a.created_at),
          })}
        </span>
        <a
          href={downloadHref(a)}
          download={a.name.split("/").pop()}
          className="ml-auto inline-flex min-h-9 items-center gap-1 text-sm text-accent"
        >
          <Download aria-hidden className="size-4" />
          {t("artifacts.download")}
        </a>
      </div>
      {older.length > 0 ? (
        <label className="flex items-center gap-2 text-sm">
          {t("artifacts.compare")}
          <select
            value={against ?? ""}
            onChange={(e) => setAgainst(e.target.value ? Number(e.target.value) : null)}
            className="min-h-9 rounded-card border border-line bg-surface px-2"
          >
            <option value="">{t("artifacts.noDiff")}</option>
            {older.map((v) => (
              <option key={v.id} value={v.version}>
                v{v.version}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {against !== null ? (
        diff.isPending ? (
          <LoadingBlock />
        ) : diff.data ? (
          <DiffView diff={diff.data.diff} />
        ) : null
      ) : (
        <ArtifactContent content={a.content} data={a.data} name={a.name} />
      )}
    </div>
  );
}
