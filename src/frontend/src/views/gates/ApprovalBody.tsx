// SPDX-License-Identifier: AGPL-3.0-or-later
import type { UseMutationResult } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api, type DecideBody } from "../../api/endpoints.ts";
import { keys } from "../../api/queries.ts";
import type { Artifact, Gate } from "../../api/types.ts";
import { Button } from "../../components/Button.tsx";
import { EmptyState, LoadingBlock } from "../../components/Feedback.tsx";
import { Tabs } from "../../components/Tabs.tsx";
import { ArtifactContent, DiffView } from "../shared/DiffView.tsx";
import { TeamProposal } from "./TeamProposal.tsx";

type Decide = UseMutationResult<Gate, Error, DecideBody>;

function ArtifactTab({ artifact }: { artifact: Artifact }) {
  const { t } = useTranslation();
  const [showDiff, setShowDiff] = useState(artifact.version > 1);
  const diff = useQuery({
    queryKey: keys.diff(artifact.id, artifact.version - 1),
    queryFn: () => api.artifactDiff(artifact.id, artifact.version - 1),
    enabled: showDiff && artifact.version > 1,
  });
  return (
    <div className="space-y-2 pt-3">
      <div className="flex items-center justify-between text-xs text-muted">
        <span className="font-mono">
          {artifact.name} v{artifact.version}
        </span>
        {artifact.version > 1 ? (
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={showDiff}
              onChange={(e) => setShowDiff(e.target.checked)}
            />
            {t("gate.diffPrevious")}
          </label>
        ) : null}
      </div>
      {showDiff && artifact.version > 1 ? (
        diff.isPending ? (
          <LoadingBlock />
        ) : (
          <DiffView diff={diff.data?.diff ?? ""} />
        )
      ) : (
        <ArtifactContent content={artifact.content} data={artifact.data} />
      )}
    </div>
  );
}

export function ApprovalBody({ gate }: { gate: Gate }) {
  const { t } = useTranslation();
  const artifacts = gate.artifacts ?? [];
  const [active, setActive] = useState(artifacts[0]?.id ?? "");
  if (artifacts.length === 0) return <EmptyState title={t("gate.noArtifacts")} />;
  const current = artifacts.find((a) => a.id === active) ?? artifacts[0];
  return (
    <div>
      {gate.payload.team ? <TeamProposal team={gate.payload.team} /> : null}
      <Tabs
        label={t("gate.artifacts")}
        idPrefix="gate-artifact"
        tabs={artifacts.map((a) => ({
          id: a.id,
          label: t(`kind.${a.kind}`, { defaultValue: a.kind }),
        }))}
        active={current?.id ?? ""}
        onChange={setActive}
      />
      {current ? <ArtifactTab key={current.id} artifact={current} /> : null}
    </div>
  );
}

export function ApprovalActions({ gate, decide }: { gate: Gate; decide: Decide }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"approve_with_comments" | "reject" | null>(null);
  const [comment, setComment] = useState("");
  const release = gate.gate_id === "approve_release";
  if (mode) {
    return (
      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          decide.mutate({ decision: mode, comment });
        }}
      >
        <label htmlFor="gate-comment" className="text-sm font-medium">
          {t(mode === "reject" ? "gate.rejectReason" : "gate.comments")}
        </label>
        {mode === "reject" && release ? (
          <p className="text-xs text-muted">{t("gate.rejectRelease")}</p>
        ) : null}
        <textarea
          id="gate-comment"
          required
          rows={4}
          autoFocus
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className="w-full rounded-card border border-line bg-bg p-2 text-sm"
        />
        <div className="flex justify-end gap-2">
          <Button onClick={() => setMode(null)}>{t("cancel")}</Button>
          <Button
            type="submit"
            variant={mode === "reject" ? "danger" : "primary"}
            busy={decide.isPending}
            disabled={!comment.trim()}
          >
            {t(mode === "reject" ? "gate.reject" : "gate.approveWithComments")}
          </Button>
        </div>
      </form>
    );
  }
  return (
    <div className="flex flex-wrap justify-end gap-2">
      <Button variant="danger" onClick={() => setMode("reject")}>
        {t("gate.reject")}
      </Button>
      <Button onClick={() => setMode("approve_with_comments")}>
        {t("gate.approveWithComments")}
      </Button>
      <Button
        variant="primary"
        busy={decide.isPending}
        onClick={() => decide.mutate({ decision: "approve" })}
      >
        {t("gate.approve")}
      </Button>
    </div>
  );
}
