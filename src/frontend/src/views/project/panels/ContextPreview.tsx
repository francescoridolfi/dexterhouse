// SPDX-License-Identifier: AGPL-3.0-or-later
// Extracted text of a context document. Untrusted: shown as plain text, never as HTML or
// Markdown (no links, no images).
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";

import { e13, e13Keys } from "../../../api/e13.ts";
import { ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { Drawer } from "../../../components/Overlay.tsx";
import { integer } from "../../../utils/format.ts";

export function ContextPreview({ docId, onClose }: { docId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const doc = useQuery({
    queryKey: e13Keys.contextDoc(docId),
    queryFn: () => e13.contextDoc(docId),
  });
  const data = doc.data?.data;
  return (
    <Drawer
      wide
      title={data ? data.title || data.filename : t("context.preview")}
      onClose={onClose}
      footer={
        <a
          href={e13.contextDownloadUrl(docId)}
          download
          className="os-pressable inline-flex min-h-8 items-center gap-1.5 rounded-full bg-white/8 px-3.5 text-sm font-medium hover:bg-white/14"
        >
          <Download aria-hidden className="size-3.5" />
          {t("context.download")}
        </a>
      }
    >
      {doc.isPending ? <LoadingBlock rows={8} /> : null}
      {doc.isError ? <ErrorState error={doc.error} onRetry={() => void doc.refetch()} /> : null}
      {doc.data ? (
        <div className="space-y-3">
          <p className="text-xs text-muted">
            {data?.chars !== undefined ? t("context.chars", { count: data.chars }) : null}
            {data?.pages ? ` · ${t("context.pages", { count: data.pages })}` : null}
            {data?.truncated
              ? ` · ${t("context.truncated", { max: integer(data.chars ?? 0) })}`
              : null}
          </p>
          {doc.data.content ? (
            <pre
              aria-label={t("context.extracted")}
              className="max-h-[70vh] overflow-auto rounded-[12px] bg-black/25 p-4 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap"
            >
              {doc.data.content}
            </pre>
          ) : (
            <p className="text-sm text-muted">{t("context.noText")}</p>
          )}
        </div>
      ) : null}
    </Drawer>
  );
}
