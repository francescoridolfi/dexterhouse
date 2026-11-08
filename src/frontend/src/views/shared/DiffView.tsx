// SPDX-License-Identifier: AGPL-3.0-or-later
// Unified diff (from `GET /artifacts/{id}/diff`) and artifact content: rendered Markdown with a
// source view, highlighted code and JSON.
import { Suspense, lazy, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { CodeBlock } from "../../components/code/CodeBlock.tsx";
import { Tabs } from "../../components/Tabs.tsx";

export function DiffView({ diff }: { diff: string }) {
  const { t } = useTranslation();
  if (!diff.trim()) return <p className="text-sm text-muted">{t("artifacts.noChanges")}</p>;
  return (
    <pre className="overflow-x-auto rounded-[14px] border border-white/8 bg-[#0d1117]/85 p-3 font-mono text-[12.5px] leading-[1.6]">
      {diff.split("\n").map((line, index) => {
        const tone =
          line.startsWith("+") && !line.startsWith("+++")
            ? "bg-done/15 text-done"
            : line.startsWith("-") && !line.startsWith("---")
              ? "bg-failed/15 text-failed"
              : line.startsWith("@@")
                ? "text-accent"
                : "";
        return (
          <span key={index} className={`block ${tone}`}>
            {line || " "}
          </span>
        );
      })}
    </pre>
  );
}

// react-markdown + remark-gfm load with the first Markdown artifact, not with the app.
const Markdown = lazy(() =>
  import("../../components/code/Markdown.tsx").then((m) => ({ default: m.Markdown })),
);

type View = "preview" | "source";

function isMarkdown(name: string | undefined, content: string): boolean {
  const base = (name ?? "").split("/").pop() ?? "";
  if (/\.(md|markdown|mdx)$/i.test(base)) return true;
  // Agent documents without an extension are Markdown (markdown-artifacts skill).
  return !base.includes(".") && content.trim().length > 0;
}

/** Agent-written content is shown as is (never translated), labelled as such. */
export function ArtifactContent({
  content,
  data,
  name,
}: {
  content?: string;
  data?: unknown;
  name?: string;
}) {
  const { t } = useTranslation();
  const id = useId().replace(/:/g, "");
  const [view, setView] = useState<View>("preview");
  const markdown = content ? isMarkdown(name, content) : false;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="mr-auto text-xs text-muted">{t("artifacts.agentText")}</p>
        {markdown ? (
          <Tabs
            label={t("artifacts.view")}
            idPrefix={`art-${id}`}
            active={view}
            onChange={(next) => setView(next as View)}
            tabs={[
              { id: "preview", label: t("artifacts.preview") },
              { id: "source", label: t("artifacts.source") },
            ]}
          />
        ) : null}
      </div>
      {content ? (
        markdown ? (
          <div role="tabpanel" id={`art-${id}-panel-${view}`} aria-labelledby={`art-${id}-${view}`}>
            {view === "preview" ? (
              <div className="rounded-[14px] border border-line bg-black/15 px-6 py-5">
                <Suspense
                  fallback={<p className="text-sm whitespace-pre-wrap text-muted">{content}</p>}
                >
                  <Markdown source={content} />
                </Suspense>
              </div>
            ) : (
              <CodeBlock code={content} lang="markdown" title={name} />
            )}
          </div>
        ) : (
          <CodeBlock code={content} lang={name} title={name} />
        )
      ) : null}
      {data !== null && data !== undefined ? (
        <CodeBlock
          code={JSON.stringify(data, null, 2)}
          lang="json"
          title={content ? "data.json" : name}
          maxHeight="max-h-[40vh]"
        />
      ) : null}
    </div>
  );
}
