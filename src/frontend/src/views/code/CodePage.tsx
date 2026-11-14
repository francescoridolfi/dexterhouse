// SPDX-License-Identifier: AGPL-3.0-or-later
// The Code app: one window per project (`/code/<id>?path=…&line=…&ref=…`). Files on the
// left, the file in the middle, "Location" on the right; narrow windows show one at a time.
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, FolderTree, MapPin, Network } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client.ts";
import { api } from "../../api/endpoints.ts";
import { keys } from "../../api/queries.ts";
import { Button } from "../../components/Button.tsx";
import { Card, EmptyState, ErrorState, LoadingBlock } from "../../components/Feedback.tsx";
import { CODE_GRAPH_KIND } from "../graph/graphModel.ts";
import { CodeProjectPicker } from "./CodeProjectPicker.tsx";
import { FileTree } from "./FileTree.tsx";
import { FileView } from "./FileView.tsx";
import { codeHref, graphHref, parseCodeSearch } from "./links.ts";
import { LocationPanel } from "./LocationPanel.tsx";

function Toolbar({
  projectId,
  path,
  refLabel,
  pinned,
  line,
  onFiles,
  onLocation,
  locationOpen,
}: {
  projectId: string;
  path: string | null;
  refLabel: string;
  pinned: boolean;
  line: number | null;
  onFiles: () => void;
  onLocation: () => void;
  locationOpen: boolean;
}) {
  const { t } = useTranslation();
  const project = useQuery({
    queryKey: keys.project(projectId),
    queryFn: () => api.project(projectId),
  });
  const graphs = useQuery({
    queryKey: keys.artifacts(projectId, `kind:${CODE_GRAPH_KIND}`),
    queryFn: () => api.artifacts(projectId, { kind: CODE_GRAPH_KIND }),
  });
  const graph = (graphs.data?.results ?? []).reduce<{ id: string; version: number } | null>(
    (best, a) => (best && best.version >= a.version ? best : a),
    null,
  );
  return (
    <div className="flex flex-wrap items-center gap-2">
      {path ? (
        <button
          type="button"
          onClick={onFiles}
          className="os-pressable inline-flex min-h-8 items-center gap-1 rounded-full bg-white/8 px-3 text-sm @3xl:hidden"
        >
          <ChevronLeft aria-hidden className="size-4" />
          {t("codeApp.files")}
        </button>
      ) : null}
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[17px] font-semibold tracking-tight">
          <Link to={`/projects/${projectId}`} className="hover:underline">
            {project.data?.name ?? "…"}
          </Link>
        </h1>
        <p className="flex items-center gap-2 truncate font-mono text-xs text-muted">
          {refLabel}
          {pinned ? (
            <Link
              to={codeHref(projectId, { path, line })}
              className="font-sans text-accent hover:underline"
            >
              {t("codeApp.latest")}
            </Link>
          ) : null}
        </p>
      </div>
      {graph ? (
        <Link
          to={graphHref(graph.id)}
          className="os-pressable inline-flex min-h-8 items-center gap-1.5 rounded-full bg-white/8 px-3 text-sm hover:bg-white/14"
        >
          <Network aria-hidden className="size-3.5" />
          {t("graph.title")}
        </Link>
      ) : null}
      <Button
        size="sm"
        className="rounded-full @6xl:hidden"
        aria-expanded={locationOpen}
        aria-controls="code-location"
        icon={<MapPin aria-hidden className="size-3.5" />}
        onClick={onLocation}
      >
        {t("codeApp.location")}
      </Button>
    </div>
  );
}

function CodeWorkspace({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { path, line, ref: rev } = parseCodeSearch(location.search);
  const [filesOpen, setFilesOpen] = useState(false);
  const [locationOpen, setLocationOpen] = useState(false);
  const tree = useQuery({
    queryKey: keys.codeTree(projectId, rev),
    queryFn: () => api.codeTree(projectId, rev),
    staleTime: rev === "HEAD" ? 15_000 : Infinity,
    retry: (count, error) => !(error instanceof ApiError) && count < 2,
  });
  const go = (target: { path: string; line?: number | null }) => {
    setFilesOpen(false);
    void navigate(codeHref(projectId, { ...target, ref: rev }));
  };
  const sha = tree.data?.commit.slice(0, 8) ?? rev.slice(0, 8);
  const refLabel =
    rev !== "HEAD"
      ? t("codeApp.atCommit", { sha })
      : tree.data
        ? `${tree.data.branch ?? "HEAD"} @ ${sha}`
        : "HEAD";
  const unavailable = tree.error instanceof ApiError && tree.error.status === 503;
  const showTree = !path || filesOpen;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <Toolbar
        projectId={projectId}
        path={path}
        refLabel={refLabel}
        pinned={rev !== "HEAD"}
        line={line}
        onFiles={() => setFilesOpen(true)}
        onLocation={() => setLocationOpen(!locationOpen)}
        locationOpen={locationOpen}
      />
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] gap-3 @3xl:grid-cols-[15rem_minmax(0,1fr)] @6xl:grid-cols-[15rem_minmax(0,1fr)_18rem]">
        <aside
          aria-label={t("codeApp.files")}
          className={`min-h-0 flex-col ${showTree ? "flex" : "hidden"} @3xl:flex`}
        >
          {tree.isPending ? (
            <LoadingBlock rows={6} />
          ) : tree.isError ? (
            unavailable ? null : (
              <ErrorState error={tree.error} onRetry={() => void tree.refetch()} />
            )
          ) : (
            <FileTree
              entries={tree.data.entries}
              selected={path}
              onSelect={(next) => go({ path: next })}
            />
          )}
        </aside>
        <section
          aria-label={t("codeApp.viewer")}
          className={`min-h-0 flex-col ${showTree ? "hidden" : "flex"} @3xl:flex`}
        >
          {unavailable ? (
            <EmptyState title={t("codeApp.unavailable")}>{tree.error?.message}</EmptyState>
          ) : path ? (
            <FileView
              projectId={projectId}
              path={path}
              line={line}
              rev={rev}
              onLine={(n) => go({ path, line: n })}
            />
          ) : (
            <EmptyState
              icon={<FolderTree aria-hidden className="size-8" />}
              title={t("codeApp.pick")}
            >
              {tree.data?.truncated ? t("codeApp.truncated") : null}
            </EmptyState>
          )}
        </section>
        <div
          id="code-location"
          className={`${locationOpen ? "block" : "hidden"} min-h-0 overflow-auto @max-3xl:order-first @3xl:col-span-2 @6xl:col-span-1 @6xl:block`}
        >
          <Card title={t("codeApp.location")}>
            <div className="p-4">
              <LocationPanel projectId={projectId} />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

export function CodePage() {
  const { projectId } = useParams();
  if (!projectId) return <CodeProjectPicker />;
  return <CodeWorkspace key={projectId} projectId={projectId} />;
}
