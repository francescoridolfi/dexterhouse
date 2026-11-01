// SPDX-License-Identifier: AGPL-3.0-or-later
// Unified diff (from `GET /artifacts/{id}/diff`) and artifact content (Markdown/JSON as text).
import { useTranslation } from "react-i18next";

export function DiffView({ diff }: { diff: string }) {
  const { t } = useTranslation();
  if (!diff.trim()) return <p className="text-sm text-muted">{t("artifacts.noChanges")}</p>;
  return (
    <pre className="overflow-x-auto rounded-card border border-line bg-bg p-3 font-mono text-xs leading-5">
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

/** Agent-written content is shown as is (never translated), labelled as such. */
export function ArtifactContent({ content, data }: { content?: string; data?: unknown }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted">{t("artifacts.agentText")}</p>
      {content ? (
        <pre className="max-h-[60vh] overflow-auto rounded-card border border-line bg-bg p-3 font-mono text-xs whitespace-pre-wrap">
          {content}
        </pre>
      ) : null}
      {data !== null && data !== undefined ? (
        <pre className="max-h-[40vh] overflow-auto rounded-card border border-line bg-bg p-3 font-mono text-xs">
          {JSON.stringify(data, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
