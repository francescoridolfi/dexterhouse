// SPDX-License-Identifier: AGPL-3.0-or-later
// Changes tab (docs/specs/change-requests.md, UI): the project's change requests, newest
// first, and the form to write one. Live through `change_request.*` events.
import { GitPullRequestArrow, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ChangeRequest } from "../../../api/e13.ts";
import { useMe } from "../../../api/queries.ts";
import { Button } from "../../../components/Button.tsx";
import { Card, EmptyState, ErrorState, LoadingBlock } from "../../../components/Feedback.tsx";
import { useProjectStore } from "../../../store/projectStore.ts";
import { can } from "../../../utils/auth.ts";
import { useChangeRequests } from "../live.ts";
import { ChangeRequestForm } from "../panels/ChangeRequestForm.tsx";
import { ChangeRequestRow } from "../panels/ChangeRequestRow.tsx";

export function ChangesTab() {
  const { t } = useTranslation();
  const me = useMe();
  const projectId = useProjectStore((s) => s.projectId ?? "");
  const status = useProjectStore((s) => s.project?.status);
  const crs = useChangeRequests(projectId);
  const [form, setForm] = useState<{ editing: ChangeRequest | null } | null>(null);
  const member = can(me.data, "member") && status !== "archived";
  const admin = can(me.data, "admin") && status !== "archived";
  const rows = [...(crs.data?.results ?? [])].sort((a, b) => b.number - a.number);
  return (
    <Card
      title={t("cr.title")}
      actions={
        member ? (
          <Button
            size="sm"
            variant="primary"
            className="rounded-full px-3 normal-case"
            icon={<Plus aria-hidden className="size-3.5" />}
            onClick={() => setForm({ editing: null })}
          >
            {t("cr.new")}
          </Button>
        ) : null
      }
    >
      {crs.isPending ? <LoadingBlock rows={3} /> : null}
      {crs.isError ? <ErrorState error={crs.error} onRetry={() => void crs.refetch()} /> : null}
      {crs.isSuccess && rows.length === 0 ? (
        <EmptyState
          title={t("cr.empty")}
          icon={<GitPullRequestArrow aria-hidden className="size-7" />}
        >
          {t("cr.emptyHelp")}
        </EmptyState>
      ) : null}
      {rows.length ? (
        <ul className="divide-y divide-line" aria-label={t("cr.title")}>
          {rows.map((cr) => (
            <ChangeRequestRow
              key={cr.id}
              cr={cr}
              member={member}
              admin={admin}
              projectCompleted={status === "completed"}
              onEdit={() => setForm({ editing: cr })}
            />
          ))}
        </ul>
      ) : null}
      {form ? (
        <ChangeRequestForm
          projectId={projectId}
          editing={form.editing}
          onClose={() => setForm(null)}
        />
      ) : null}
    </Card>
  );
}
