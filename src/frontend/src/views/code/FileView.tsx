// SPDX-License-Identifier: AGPL-3.0-or-later
// One file of the workspace at a ref, highlighted by Shiki; the deep-linked line is marked.
import { useQuery } from "@tanstack/react-query";
import { FileQuestion, Link2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ApiError } from "../../api/client.ts";
import { api } from "../../api/endpoints.ts";
import { keys } from "../../api/queries.ts";
import { CodeBlock } from "../../components/code/CodeBlock.tsx";
import { EmptyState, ErrorState, LoadingBlock } from "../../components/Feedback.tsx";
import { formatSize } from "./treeModel.ts";
import { codeHref } from "./links.ts";

export function FileView({
  projectId,
  path,
  line,
  rev,
  onLine,
}: {
  projectId: string;
  path: string;
  line: number | null;
  rev: string;
  onLine: (line: number) => void;
}) {
  const { t } = useTranslation();
  const file = useQuery({
    queryKey: keys.codeFile(projectId, rev, path),
    queryFn: () => api.codeFile(projectId, path, rev),
    staleTime: rev === "HEAD" ? 15_000 : Infinity,
    retry: (count, error) => !(error instanceof ApiError) && count < 2,
  });

  if (file.isPending) return <LoadingBlock rows={8} />;
  if (file.isError) {
    if (file.error instanceof ApiError && file.error.status === 404)
      return (
        <EmptyState
          icon={<FileQuestion aria-hidden className="size-8" />}
          title={t("codeApp.missing")}
        >
          <span className="font-mono">{path}</span>
        </EmptyState>
      );
    return <ErrorState error={file.error} onRetry={() => void file.refetch()} />;
  }
  const data = file.data;
  if (data.binary || data.too_large || data.content === null)
    return (
      <EmptyState
        icon={<FileQuestion aria-hidden className="size-8" />}
        title={data.binary ? t("codeApp.binary") : t("codeApp.tooLarge")}
      >
        <span className="font-mono">
          {path} · {formatSize(data.size)}
        </span>
      </EmptyState>
    );

  const permalink = () => {
    const href = codeHref(projectId, { path, line, ref: data.commit });
    void navigator.clipboard?.writeText(window.location.origin + href);
  };

  return (
    <CodeBlock
      key={`${rev}:${path}`}
      code={data.content}
      lang={path}
      title={path}
      highlight={line}
      onLine={onLine}
      maxHeight="flex-1"
      className="h-full"
      actions={
        <button
          type="button"
          onClick={permalink}
          aria-label={t("codeApp.permalink")}
          title={t("codeApp.permalink")}
          className="grid size-6 place-items-center rounded-md hover:bg-white/10 hover:text-fg"
        >
          <Link2 aria-hidden className="size-3.5" />
        </button>
      }
    />
  );
}
