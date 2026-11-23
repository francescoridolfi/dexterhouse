// SPDX-License-Identifier: AGPL-3.0-or-later
// New / edit change request (draft only): title, Markdown body, budget, attachments. The
// attachments go through the context upload with `change_request` set.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, Suspense, lazy, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "../../../api/client.ts";
import { type ChangeRequest, e13, e13Keys, uploadContextFiles } from "../../../api/e13.ts";
import { AmountField } from "../../../components/AmountField.tsx";
import { Button } from "../../../components/Button.tsx";
import { FileDrop } from "../../../components/FileDrop.tsx";
import { TextField } from "../../../components/Fields.tsx";
import { Drawer } from "../../../components/Overlay.tsx";
import { Tabs } from "../../../components/Tabs.tsx";
import { toastError, toastSuccess } from "../../../components/toastStore.ts";
import { formatAmount, parseAmount } from "../../../utils/amount.ts";

const Markdown = lazy(() =>
  import("../../../components/code/Markdown.tsx").then((m) => ({ default: m.Markdown })),
);
const BODY_MAX = 20_000;

export function ChangeRequestForm({
  projectId,
  editing,
  onClose,
}: {
  projectId: string;
  editing: ChangeRequest | null;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const client = useQueryClient();
  const [title, setTitle] = useState(editing?.title ?? "");
  const [body, setBody] = useState(editing?.body ?? "");
  const [budget, setBudget] = useState(
    editing ? formatAmount(Number(editing.budget), i18n.language) : "10",
  );
  const [files, setFiles] = useState<File[]>([]);
  const [view, setView] = useState<"write" | "preview">("write");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const amount = parseAmount(budget);
  const save = useMutation({
    mutationFn: async () => {
      const input = { title: title.trim(), body, budget: String(amount ?? 0) };
      const cr = editing
        ? await e13.updateChangeRequest(editing.id, input)
        : await e13.createChangeRequest(projectId, input);
      return { cr, failed: await uploadContextFiles(projectId, files, cr.id) };
    },
    onSuccess: ({ cr, failed }) => {
      for (const f of failed) {
        toastError(t("context.uploadFailed", { name: f.name }), new Error(f.reason));
      }
      toastSuccess(t(editing ? "cr.saved" : "cr.created", { n: cr.number }));
      void client.invalidateQueries({ queryKey: e13Keys.changeRequests(projectId) });
      void client.invalidateQueries({ queryKey: e13Keys.context(projectId) });
      onClose();
    },
    onError: (error) => {
      if (error instanceof ApiError) setErrors(error.fieldErrors());
      toastError(t("cr.saveFailed"), error);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setErrors({});
    if (title.trim() && body.trim() && amount !== null) save.mutate();
  };
  return (
    <Drawer
      wide
      title={editing ? t("cr.editTitle", { n: editing.number }) : t("cr.new")}
      onClose={onClose}
    >
      <form id={`${id}-form`} onSubmit={submit} className="space-y-5">
        <TextField
          label={t("cr.fieldTitle")}
          value={title}
          maxLength={120}
          required
          error={errors.title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <div className="space-y-1.5">
          <div className="flex items-end justify-between gap-3">
            <label htmlFor={`${id}-body`} className="text-sm font-medium">
              {t("cr.fieldBody")}
            </label>
            <Tabs
              label={t("newProject.briefView")}
              idPrefix={`${id}-view`}
              active={view}
              onChange={(next) => setView(next as "write" | "preview")}
              tabs={[
                { id: "write", label: t("newProject.write") },
                { id: "preview", label: t("newProject.preview") },
              ]}
            />
          </div>
          <textarea
            id={`${id}-body`}
            rows={10}
            value={body}
            maxLength={BODY_MAX}
            required
            hidden={view === "preview"}
            placeholder={t("cr.bodyPlaceholder")}
            aria-invalid={!!errors.body || undefined}
            onChange={(e) => setBody(e.target.value)}
            className="block min-h-48 w-full resize-y rounded-[12px] border border-line bg-black/20 px-3 py-2.5 font-mono text-[13px] leading-relaxed focus:border-accent/60 focus:outline-none"
          />
          {view === "preview" ? (
            <div className="min-h-48 rounded-[12px] border border-line px-4 py-3">
              <Suspense fallback={null}>{body.trim() ? <Markdown source={body} /> : null}</Suspense>
            </div>
          ) : null}
          <p className="flex justify-between text-xs text-muted">
            <span className={errors.body ? "text-failed" : ""}>
              {errors.body ?? t("newProject.markdownHint")}
            </span>
            <span className="tabular-nums">
              {t("newProject.briefCount", { count: body.length, max: BODY_MAX })}
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">{t("cr.fieldBudget")}</p>
            <p className={`text-xs ${errors.budget ? "text-failed" : "text-muted"}`}>
              {errors.budget ?? t("cr.budgetHelp")}
            </p>
          </div>
          <AmountField
            label={t("cr.fieldBudget")}
            value={budget}
            onChange={setBudget}
            decreaseLabel={t("budget.decrease")}
            increaseLabel={t("budget.increase")}
          />
        </div>
        <div className="space-y-1.5">
          <p className="text-sm font-medium">{t("cr.attachments")}</p>
          <FileDrop
            label={t("context.choose")}
            files={files}
            onChange={setFiles}
            disabled={save.isPending}
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button size="sm" className="rounded-full px-4" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button
            size="sm"
            type="submit"
            variant="primary"
            className="rounded-full px-4"
            busy={save.isPending}
            disabled={!title.trim() || !body.trim() || amount === null}
          >
            {editing ? t("save") : t("cr.create")}
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
