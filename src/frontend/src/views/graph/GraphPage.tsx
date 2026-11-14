// SPDX-License-Identifier: AGPL-3.0-or-later
// The Graph app: a `code_graph` artifact in its own window (`/graph/<artifact id>`).
import { useQuery } from "@tanstack/react-query";
import { CodeXml } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/endpoints.ts";
import { keys } from "../../api/queries.ts";
import { EmptyState, ErrorState, LoadingBlock } from "../../components/Feedback.tsx";
import { dateTime } from "../../utils/format.ts";
import { codeHref } from "../code/links.ts";
import { CodeGraphView } from "./CodeGraphView.tsx";
import { parseCodeGraph } from "./graphModel.ts";

export function GraphPage() {
  const { t } = useTranslation();
  const { artifactId = "" } = useParams();
  const artifact = useQuery({
    queryKey: keys.artifact(artifactId),
    queryFn: () => api.artifact(artifactId),
  });
  if (artifact.isPending) return <LoadingBlock rows={6} />;
  if (artifact.isError)
    return <ErrorState error={artifact.error} onRetry={() => void artifact.refetch()} />;
  const a = artifact.data;
  const graph = parseCodeGraph(a.data);
  if (!graph) return <EmptyState title={t("graph.invalid")} />;
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <header className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[17px] font-semibold tracking-tight">
            {a.name} <span className="text-muted">v{a.version}</span>
          </h1>
          <p className="truncate text-xs text-muted">
            {t("graph.summary", { nodes: graph.nodes.length, edges: graph.edges.length })}
            {graph.commit ? ` · ${graph.commit.slice(0, 8)}` : ""}
            {graph.generatedAt ? ` · ${dateTime(graph.generatedAt)}` : ""}
          </p>
        </div>
        <Link
          to={codeHref(a.project, { ref: graph.commit })}
          className="os-pressable inline-flex min-h-8 items-center gap-1.5 rounded-full bg-white/8 px-3 text-sm hover:bg-white/14"
        >
          <CodeXml aria-hidden className="size-3.5" />
          {t("codeApp.short")}
        </Link>
      </header>
      <CodeGraphView graph={graph} projectId={a.project} fill />
    </div>
  );
}
