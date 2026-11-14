// SPDX-License-Identifier: AGPL-3.0-or-later
// "Where is the code": the workspace in the runner, branch and HEAD, the delivered releases
// (branch, pull request) and ready-to-copy commands to get it on your machine.
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  Copy,
  ExternalLink,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/endpoints.ts";
import { keys } from "../../api/queries.ts";
import type { CodeLocation } from "../../api/types.ts";
import { ErrorState, LoadingBlock } from "../../components/Feedback.tsx";
import { dateTime } from "../../utils/format.ts";
import { commands } from "./location.ts";

const short = (sha: string | null | undefined) => (sha ? sha.slice(0, 8) : "—");

function CopyCommand({ label, command }: { label: string; command: string }) {
  const { t } = useTranslation();
  const [done, setDone] = useState(false);
  const copy = () =>
    void navigator.clipboard?.writeText(command).then(() => {
      setDone(true);
      window.setTimeout(() => setDone(false), 1500);
    });
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted">{label}</p>
      <div className="flex items-start gap-1 rounded-[10px] bg-black/30 py-1.5 pr-1 pl-2.5">
        <code className="min-w-0 flex-1 font-mono text-[11.5px] break-all text-[#e6edf3]">
          {command}
        </code>
        <button
          type="button"
          onClick={copy}
          aria-label={done ? t("code.copied") : t("codeApp.copyCommand", { label })}
          title={done ? t("code.copied") : t("code.copy")}
          className="grid size-7 shrink-0 place-items-center rounded-md text-muted hover:bg-white/10 hover:text-fg"
        >
          {done ? (
            <Check aria-hidden className="size-3.5 text-done" />
          ) : (
            <Copy aria-hidden className="size-3.5" />
          )}
        </button>
      </div>
    </div>
  );
}

function Row({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <span className="mt-0.5 text-muted">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs text-muted">{label}</p>
        <div className="min-w-0 break-words">{children}</div>
      </div>
    </div>
  );
}

const LINK = "inline-flex items-center gap-1 text-accent hover:underline";

export function LocationBody({ data }: { data: CodeLocation }) {
  const { t } = useTranslation();
  const latest = data.releases[0] ?? null;
  const commitUrl =
    data.web_url && latest?.commit ? `${data.web_url}/commit/${latest.commit}` : null;
  return (
    <div className="space-y-3">
      <Row icon={<GitBranch aria-hidden className="size-4" />} label={t("codeApp.workspace")}>
        {data.workspace ? (
          <>
            <span className="font-mono text-xs">{data.workspace.path}</span>{" "}
            <span className="text-muted">
              · {data.branch ?? "—"} ·{" "}
              {t(`codeApp.ws.${data.workspace.status}`, { defaultValue: data.workspace.status })}
            </span>
          </>
        ) : (
          <span className="text-muted">{t("codeApp.noWorkspace")}</span>
        )}
      </Row>
      <Row icon={<GitCommitHorizontal aria-hidden className="size-4" />} label={t("codeApp.head")}>
        {data.head ? (
          <>
            <span className="font-mono text-xs">{short(data.head.commit)}</span>{" "}
            <span>{data.head.message}</span>
            <p className="text-xs text-muted">{dateTime(data.head.date)}</p>
          </>
        ) : (
          <span className="text-muted">{data.unavailable ?? "—"}</span>
        )}
      </Row>
      <Row icon={<GitPullRequest aria-hidden className="size-4" />} label={t("codeApp.release")}>
        {latest ? (
          <>
            <span>{t("codeApp.releaseN", { n: latest.number })}</span>{" "}
            <span className="font-mono text-xs text-muted">{latest.branch}</span>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
              {latest.pr_url ? (
                <a href={latest.pr_url} target="_blank" rel="noreferrer noopener" className={LINK}>
                  {t("codeApp.openPr")} <ExternalLink aria-hidden className="size-3" />
                </a>
              ) : null}
              {commitUrl ? (
                <a href={commitUrl} target="_blank" rel="noreferrer noopener" className={LINK}>
                  {t("codeApp.openCommit", { sha: short(latest.commit) })}
                  <ExternalLink aria-hidden className="size-3" />
                </a>
              ) : null}
            </div>
          </>
        ) : (
          <span className="text-muted">
            {data.remote_url ? t("codeApp.notDelivered") : t("codeApp.noRemote")}
          </span>
        )}
      </Row>
      {commands(data).map((c) => (
        <CopyCommand key={c.id} label={t(`codeApp.cmd.${c.id}`)} command={c.command} />
      ))}
    </div>
  );
}

export function LocationPanel({ projectId }: { projectId: string }) {
  const location = useQuery({
    queryKey: keys.codeLocation(projectId),
    queryFn: () => api.codeLocation(projectId),
    refetchInterval: 30_000,
  });
  if (location.isPending) return <LoadingBlock rows={4} />;
  if (location.isError)
    return <ErrorState error={location.error} onRetry={() => void location.refetch()} />;
  return <LocationBody data={location.data} />;
}
