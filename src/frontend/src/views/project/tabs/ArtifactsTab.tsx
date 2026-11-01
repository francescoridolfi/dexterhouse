// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { keys } from "../../../api/queries.ts";
import type { Artifact } from "../../../api/types.ts";
import { Card, EmptyState, ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { useProjectStore } from "../../../store/projectStore.ts";
import { ArtifactViewer } from "../panels/ArtifactViewer.tsx";

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
          <ArtifactViewer key={selected} artifactId={selected} />
        ) : (
          <EmptyState title={t("artifacts.pick")} />
        )}
      </Card>
    </div>
  );
}
