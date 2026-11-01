// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys } from "../../../api/queries.ts";
import type { Artifact } from "../../../api/types.ts";
import { Card, EmptyState, ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { dateTime } from "../../../utils/format.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import { ArtifactContent, DiffView } from "../../shared/DiffView.tsx";

function downloadHref(artifact: Artifact): string {
  const body = artifact.content || JSON.stringify(artifact.data ?? {}, null, 2);
  return URL.createObjectURL(new Blob([body], { type: "text/plain;charset=utf-8" }));
}

function Viewer({ artifactId }: { artifactId: string }) {
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
        <ArtifactContent content={a.content} data={a.data} />
      )}
    </div>
  );
}

export function ArtifactsTab() {
  const { t } = useTranslation();
  const projectId = useProjectStore((s) => s.projectId ?? "");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const list = useQuery({
    queryKey: keys.artifacts(projectId, q),
    queryFn: () => api.artifacts(projectId, { q: q || undefined }),
  });
  const tree = useMemo(() => {
    const latest = new Map<string, Artifact>();
    for (const a of list.data?.results ?? []) {
      const key = `${a.kind}/${a.name}`;
      const current = latest.get(key);
      if (!current || current.version < a.version) latest.set(key, a);
    }
    const byKind = new Map<string, Artifact[]>();
    for (const a of latest.values()) byKind.set(a.kind, [...(byKind.get(a.kind) ?? []), a]);
    return [...byKind.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [list.data]);

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <Card title={t("artifacts.title")}>
        <div className="p-3">
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("artifacts.search")}
            aria-label={t("artifacts.search")}
            className="min-h-11 w-full rounded-card border border-line bg-bg px-3 text-sm"
          />
        </div>
        {list.isPending ? (
          <LoadingBlock />
        ) : list.isError ? (
          <ErrorState error={list.error} onRetry={() => void list.refetch()} />
        ) : tree.length === 0 ? (
          <EmptyState title={t("artifacts.empty")} />
        ) : (
          <ul className="pb-2">
            {tree.map(([kind, items]) => (
              <li key={kind}>
                <p className="px-4 pt-2 text-xs font-semibold tracking-wide text-muted uppercase">
                  {t(`kind.${kind}`, { defaultValue: kind })}
                </p>
                <ul>
                  {items.map((a) => (
                    <li key={a.id}>
                      <button
                        type="button"
                        onClick={() => setSelected(a.id)}
                        aria-current={selected === a.id || undefined}
                        className={`flex min-h-10 w-full items-center justify-between px-4 text-left font-mono text-xs hover:bg-bg ${selected === a.id ? "text-accent" : ""}`}
                      >
                        <span className="truncate">{a.name}</span>
                        <span className="text-muted">v{a.version}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title={t("artifacts.viewer")}>
        {selected ? (
          <Viewer key={selected} artifactId={selected} />
        ) : (
          <EmptyState title={t("artifacts.pick")} />
        )}
      </Card>
    </div>
  );
}
