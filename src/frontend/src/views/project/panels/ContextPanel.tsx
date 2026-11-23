// SPDX-License-Identifier: AGPL-3.0-or-later
// Context documents of the project (docs/specs/context-documents.md, UI): list, upload,
// plain-text preview, download, deactivate. Live through `context.*` events.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FileText, Loader2, Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  type ContextDocument,
  e13,
  e13Keys,
  personName,
  uploadContextFiles,
} from "../../../api/e13.ts";
import { useMe } from "../../../api/queries.ts";
import { Card, EmptyState, ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { CONTEXT_ACCEPT } from "../../../components/FileDrop.tsx";
import { ConfirmDialog } from "../../../components/Overlay.tsx";
import { toastError } from "../../../components/toastStore.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import { can } from "../../../utils/auth.ts";
import { bytes, relative } from "../../../utils/format.ts";
import { useInvalidateOn } from "../live.ts";
import { ContextPreview } from "./ContextPreview.tsx";

const EVENTS = ["context."] as const;
const icon =
  "grid size-7 place-items-center rounded-full text-muted hover:bg-white/10 hover:text-fg";

function StatusLine({ doc }: { doc: ContextDocument }) {
  const { t } = useTranslation();
  const { status, error } = doc.data;
  if (status === "processing")
    return (
      <span className="inline-flex items-center gap-1 text-blocked">
        <Loader2 aria-hidden className="size-3 animate-spin" />
        {t("context.status.processing")}
      </span>
    );
  if (status === "failed")
    return (
      <span className="text-failed">
        {t("context.status.failed")}
        {error ? `: ${t(`context.reason.${error}`, { defaultValue: error })}` : ""}
      </span>
    );
  return <span className="text-done">{t("context.status.processed")}</span>;
}

export function ContextPanel() {
  const { t } = useTranslation();
  const me = useMe();
  const client = useQueryClient();
  const inputId = useId();
  const projectId = useProjectStore((s) => s.projectId ?? "");
  const archived = useProjectStore((s) => s.project?.status === "archived");
  const key = e13Keys.context(projectId);
  useInvalidateOn(EVENTS, key);
  const docs = useQuery({
    queryKey: key,
    queryFn: () => e13.contextDocs(projectId),
    enabled: !!projectId,
    // Fallback while extraction runs, in case the socket is reconnecting.
    refetchInterval: (q) =>
      q.state.data?.results.some((d) => d.data.status === "processing") ? 5_000 : false,
  });
  const [preview, setPreview] = useState<string | null>(null);
  const [removing, setRemoving] = useState<ContextDocument | null>(null);
  const upload = useMutation({
    mutationFn: (files: File[]) => uploadContextFiles(projectId, files),
    onSuccess: (failed) => {
      for (const f of failed)
        toastError(t("context.uploadFailed", { name: f.name }), new Error(f.reason));
    },
    onSettled: () => void client.invalidateQueries({ queryKey: key }),
  });
  const deactivate = useMutation({
    mutationFn: (id: string) => e13.deactivateContext(id),
    onSuccess: () => setRemoving(null),
    onError: (error) => toastError(t("context.deactivateFailed"), error),
    onSettled: () => void client.invalidateQueries({ queryKey: key }),
  });
  const member = can(me.data, "member") && !archived;
  const admin = can(me.data, "admin");
  const mayRemove = (doc: ContextDocument) => {
    const by = doc.data.uploaded_by;
    const id = typeof by === "object" && by ? by.id : by;
    return member && (admin || id === me.data?.id);
  };

  const action = member ? (
    <label
      htmlFor={inputId}
      className="os-pressable inline-flex min-h-7 cursor-pointer items-center gap-1 rounded-full bg-white/8 px-3 text-xs font-medium text-fg normal-case hover:bg-white/14 has-focus-visible:outline-2 has-focus-visible:outline-accent"
    >
      {upload.isPending ? (
        <Loader2 aria-hidden className="size-3.5 animate-spin" />
      ) : (
        <Plus aria-hidden className="size-3.5" />
      )}
      {t("context.upload")}
      <input
        id={inputId}
        type="file"
        multiple
        accept={CONTEXT_ACCEPT}
        className="sr-only"
        disabled={upload.isPending}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) upload.mutate(files);
        }}
      />
    </label>
  ) : null;

  const rows = docs.data?.results ?? [];
  return (
    <Card title={t("context.title")} actions={action}>
      {docs.isPending ? <LoadingBlock rows={2} /> : null}
      {docs.isError ? <ErrorState error={docs.error} onRetry={() => void docs.refetch()} /> : null}
      {docs.isSuccess && rows.length === 0 ? (
        <EmptyState title={t("context.empty")} icon={<FileText aria-hidden className="size-7" />}>
          {t("context.emptyHelp")}
        </EmptyState>
      ) : null}
      {rows.length ? (
        <ul className="divide-y divide-line" aria-label={t("context.title")}>
          {rows.map((doc) => {
            const who = personName(doc.data.uploaded_by, me.data?.id, t("context.you"));
            return (
              <li key={doc.id} className="flex items-center gap-3 px-4 py-2.5">
                <FileText aria-hidden className="size-4 shrink-0 text-muted" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {doc.data.title || doc.data.filename}
                  </p>
                  <p className="flex flex-wrap gap-x-1.5 text-xs text-muted">
                    <span className="tabular-nums">{bytes(doc.data.size)}</span>
                    <span aria-hidden>·</span>
                    <StatusLine doc={doc} />
                    <span aria-hidden>·</span>
                    <span>
                      {who ? `${who}, ` : ""}
                      {relative(doc.created_at)}
                    </span>
                  </p>
                </div>
                {doc.data.status === "processed" ? (
                  <button
                    type="button"
                    className={icon}
                    aria-label={t("context.previewOf", { name: doc.data.filename })}
                    title={t("context.preview")}
                    onClick={() => setPreview(doc.id)}
                  >
                    <Eye aria-hidden className="size-4" />
                  </button>
                ) : null}
                <a
                  href={e13.contextDownloadUrl(doc.id)}
                  download
                  className={icon}
                  aria-label={t("context.downloadOf", { name: doc.data.filename })}
                  title={t("context.download")}
                >
                  <Download aria-hidden className="size-4" />
                </a>
                {mayRemove(doc) ? (
                  <button
                    type="button"
                    className={icon}
                    aria-label={t("context.deactivateOf", { name: doc.data.filename })}
                    title={t("context.deactivate")}
                    onClick={() => setRemoving(doc)}
                  >
                    <Trash2 aria-hidden className="size-4" />
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
      {preview ? <ContextPreview docId={preview} onClose={() => setPreview(null)} /> : null}
      {removing ? (
        <ConfirmDialog
          danger
          title={t("context.deactivateTitle", { name: removing.data.filename })}
          message={t("context.deactivateMessage")}
          confirmLabel={t("context.deactivate")}
          busy={deactivate.isPending}
          onConfirm={() => deactivate.mutate(removing.id)}
          onCancel={() => setRemoving(null)}
        />
      ) : null}
    </Card>
  );
}
