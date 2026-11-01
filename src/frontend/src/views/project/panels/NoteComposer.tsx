// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../../api/endpoints.ts";
import { useMe } from "../../../api/queries.ts";
import { Button } from "../../../components/Button.tsx";
import { toastError } from "../../../components/toastStore.ts";
import { can } from "../../../utils/auth.ts";
import { useProjectStore } from "../../../store/projectStore.ts";

/** Flow F5: always visible under the log; "current phase" or "all phases". */
export function NoteComposer() {
  const { t } = useTranslation();
  const me = useMe();
  const projectId = useProjectStore((s) => s.projectId);
  const current = useProjectStore((s) =>
    Object.values(s.phases).find(
      (p) => p.status === "running" || p.status === "waiting_gate" || p.status === "reopened",
    ),
  );
  const [content, setContent] = useState("");
  const [scope, setScope] = useState<"phase" | "all">("phase");
  const send = useMutation({
    mutationFn: () =>
      api.addNote(projectId ?? "", content, scope === "phase" ? (current?.runId ?? null) : null),
    onSuccess: () => setContent(""),
    onError: (error) => toastError(t("note.failed"), error),
  });
  if (!can(me.data, "member")) return null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (content.trim()) send.mutate();
  };
  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-center gap-2 rounded-card border border-line bg-surface p-3 shadow-card"
    >
      <label htmlFor="note" className="text-xs font-semibold tracking-wide text-muted uppercase">
        {t("note.title")}
      </label>
      <input
        id="note"
        value={content}
        maxLength={10_000}
        onChange={(e) => setContent(e.target.value)}
        placeholder={t("note.placeholder")}
        className="min-h-11 min-w-48 flex-1 rounded-card border border-line bg-bg px-3 text-sm"
      />
      <fieldset className="flex items-center gap-3 text-sm">
        <legend className="sr-only">{t("note.recipient")}</legend>
        <label className="flex items-center gap-1">
          <input
            type="radio"
            name="note-scope"
            checked={scope === "phase"}
            disabled={!current}
            onChange={() => setScope("phase")}
          />
          {t("note.currentPhase")}
        </label>
        <label className="flex items-center gap-1">
          <input
            type="radio"
            name="note-scope"
            checked={scope === "all"}
            onChange={() => setScope("all")}
          />
          {t("note.all")}
        </label>
      </fieldset>
      <Button type="submit" variant="primary" busy={send.isPending} disabled={!content.trim()}>
        {t("note.send")}
      </Button>
    </form>
  );
}
