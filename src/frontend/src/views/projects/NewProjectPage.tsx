// SPDX-License-Identifier: AGPL-3.0-or-later
// New project, flow F1: one page, "save draft" or "start" (target < 60 s, NFR-U1). Laid out
// like a macOS document sheet: the name as the title, the brief as an editor with a preview,
// grouped settings, and an action bar pinned to the bottom of the window.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Eye, Play, Sparkles, Zap } from "lucide-react";
import { type FormEvent, Suspense, lazy, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client.ts";
import { api, type NewProject } from "../../api/endpoints.ts";
import { keys, useMeta } from "../../api/queries.ts";
import { AmountField } from "../../components/AmountField.tsx";
import { Button } from "../../components/Button.tsx";
import { Tabs } from "../../components/Tabs.tsx";
import { toastError } from "../../components/toastStore.ts";
import { parseAmount } from "../../utils/amount.ts";
import { eur } from "../../utils/format.ts";
import { Group, InlineInput, InlineSelect, Row } from "../settings/parts.tsx";

const Markdown = lazy(() =>
  import("../../components/code/Markdown.tsx").then((m) => ({ default: m.Markdown })),
);

const BRIEF_MAX = 20_000;
const MODES = [
  { id: "supervised", icon: Eye, tint: "text-supervised", ring: "ring-supervised/60" },
  { id: "autonomous", icon: Zap, tint: "text-autonomous", ring: "ring-autonomous/60" },
] as const;

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <span id={id} role="alert" className="text-failed">
      {message}
    </span>
  );
}

export function NewProjectPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const meta = useMeta();
  const id = useId();
  const [form, setForm] = useState<NewProject>({
    name: "",
    brief: "",
    process: "software-house-default",
    execution_mode: "supervised",
    budget: "20",
    remote_repo_url: "",
    remote_token: "",
    delivery_mode: "pull_request",
    data_residency: "any",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [advanced, setAdvanced] = useState(false);
  const [briefView, setBriefView] = useState<"write" | "preview">("write");
  const estimate = useQuery({
    queryKey: keys.estimate(form.process ?? "", Math.round(form.brief.length / 500) * 500),
    queryFn: () => api.estimate(form.process ?? "software-house-default", form.brief.length),
    staleTime: 60_000,
  });

  const save = useMutation({
    mutationFn: async (start: boolean) => {
      const amount = parseAmount(form.budget);
      const body = {
        ...form,
        budget: amount === null ? form.budget : String(amount),
        remote_repo_url: form.remote_repo_url || null,
        remote_token: form.remote_token || null,
      };
      const project = await api.createProject(body);
      if (start) {
        try {
          await api.projectAction(project.id, "start");
        } catch (error) {
          void navigate(`/projects/${project.id}`);
          throw error;
        }
      }
      return project;
    },
    onSuccess: (project) => {
      void client.invalidateQueries({ queryKey: ["projects"] });
      void navigate(`/projects/${project.id}`);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        setErrors(fields);
        if (fields.remote_repo_url || fields.remote_token) setAdvanced(true);
      }
      toastError(t("newProject.failed"), error);
    },
  });

  const set = <K extends keyof NewProject>(key: K, value: NewProject[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const submit = (start: boolean) => (event?: FormEvent) => {
    event?.preventDefault();
    setErrors({});
    save.mutate(start);
  };

  const summary = Object.keys(errors).length > 2;
  const processes = meta.data?.processes ?? [
    { name: "software-house-default", version: "", phases: [], requirements: {} },
  ];
  const process = processes.find((p) => p.name === form.process);
  const estimateText = estimate.data
    ? t("newProject.estimate", {
        low: eur(estimate.data.low, 0),
        high: eur(estimate.data.high, 0),
        basis: t(`estimate.${estimate.data.basis}`),
      })
    : null;

  return (
    <form onSubmit={submit(true)} className="mx-auto flex min-h-full max-w-3xl flex-col">
      <div className="flex-1 space-y-7 pt-2 pb-6">
        <header className="space-y-1">
          <p className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-accent uppercase">
            <Sparkles aria-hidden className="size-3.5" />
            {t("newProject.title")}
          </p>
          <label htmlFor={`${id}-name`} className="sr-only">
            {t("newProject.name")}
          </label>
          <input
            id={`${id}-name`}
            value={form.name}
            maxLength={120}
            required
            autoFocus
            autoComplete="off"
            placeholder={t("newProject.namePlaceholder")}
            aria-invalid={!!errors.name || undefined}
            aria-describedby={errors.name ? `${id}-name-error` : undefined}
            onChange={(e) => set("name", e.target.value)}
            className="w-full bg-transparent text-[28px] leading-tight font-semibold tracking-tight placeholder:text-white/25 focus:outline-none"
          />
          <p className="text-sm text-muted">
            {errors.name ? (
              <FieldError id={`${id}-name-error`} message={errors.name} />
            ) : (
              t("newProject.subtitle")
            )}
          </p>
        </header>

        {summary ? (
          <div
            role="alert"
            className="rounded-[14px] bg-failed/10 px-4 py-3 text-sm text-failed shadow-[inset_0_0_0_0.5px_rgb(248_113_113/0.4)]"
          >
            {t("newProject.fixErrors", { count: Object.keys(errors).length })}
          </div>
        ) : null}

        {/* Brief: an editor with a Markdown preview. */}
        <section className="space-y-1.5">
          <div className="flex items-end justify-between gap-3 px-3">
            <label htmlFor={`${id}-brief`} className="text-[13px] font-semibold text-fg/85">
              {t("newProject.brief")}
            </label>
            <Tabs
              label={t("newProject.briefView")}
              idPrefix={`${id}-brief-view`}
              active={briefView}
              onChange={(next) => setBriefView(next as "write" | "preview")}
              tabs={[
                { id: "write", label: t("newProject.write") },
                { id: "preview", label: t("newProject.preview") },
              ]}
            />
          </div>
          <div
            className={`overflow-hidden rounded-[14px] border bg-black/20 shadow-[inset_0_1px_2px_rgb(0_0_0/0.25)] transition-colors focus-within:border-accent/60 ${
              errors.brief ? "border-failed/70" : "border-line"
            }`}
          >
            <textarea
              id={`${id}-brief`}
              rows={12}
              value={form.brief}
              maxLength={BRIEF_MAX}
              required
              placeholder={t("newProject.briefPlaceholder")}
              aria-invalid={!!errors.brief || undefined}
              aria-describedby={`${id}-brief-count`}
              hidden={briefView === "preview"}
              onChange={(e) => set("brief", e.target.value)}
              className="block min-h-64 w-full resize-y bg-transparent px-4 py-3.5 font-mono text-[13px] leading-relaxed placeholder:text-white/25 focus:outline-none"
            />
            {briefView === "preview" ? (
              <div className="min-h-64 px-5 py-4">
                {form.brief.trim() ? (
                  <Suspense fallback={null}>
                    <Markdown source={form.brief} />
                  </Suspense>
                ) : (
                  <p className="text-sm text-muted">{t("newProject.previewEmpty")}</p>
                )}
              </div>
            ) : null}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-white/6 bg-white/3 px-4 py-2 text-xs text-muted">
              <span>{t("newProject.markdownHint")}</span>
              <span id={`${id}-brief-count`} className="ml-auto tabular-nums">
                {t("newProject.briefCount", { count: form.brief.length, max: BRIEF_MAX })}
              </span>
            </div>
          </div>
          {errors.brief ? (
            <p className="px-3 text-xs">
              <FieldError id={`${id}-brief-error`} message={errors.brief} />
            </p>
          ) : null}
        </section>

        {/* How the team works. */}
        <Group title={t("newProject.teamGroup")}>
          <Row
            label={t("newProject.process")}
            htmlFor={`${id}-process`}
            description={
              errors.process ? (
                <FieldError id={`${id}-process-error`} message={errors.process} />
              ) : process?.phases.length ? (
                t("newProject.phases", {
                  count: process.phases.length,
                  list: process.phases
                    .map((p) => t(`phase.${p.id}`, { defaultValue: p.id }))
                    .join(" → "),
                })
              ) : undefined
            }
          >
            <InlineSelect
              id={`${id}-process`}
              className="w-60"
              value={form.process}
              onChange={(e) => set("process", e.target.value)}
            >
              {processes.map((p) => (
                <option key={p.name} value={p.name}>
                  {t(`process.${p.name}`, { defaultValue: p.name })}
                </option>
              ))}
            </InlineSelect>
          </Row>
          <fieldset className="px-4 py-3">
            <legend className="mb-2.5 float-left w-full text-sm">{t("newProject.mode")}</legend>
            <div className="clear-both grid gap-2 @xl:grid-cols-2">
              {MODES.map(({ id: mode, icon: Icon, tint, ring }) => {
                const checked = form.execution_mode === mode;
                return (
                  <label
                    key={mode}
                    className={`relative flex cursor-pointer gap-3 rounded-[12px] p-3 transition-[background,box-shadow] ${
                      checked
                        ? `bg-white/8 ring-2 ${ring}`
                        : "bg-white/3 ring-1 ring-white/8 hover:bg-white/6"
                    } has-focus-visible:outline-2 has-focus-visible:outline-accent`}
                  >
                    <input
                      type="radio"
                      name={`${id}-mode`}
                      value={mode}
                      checked={checked}
                      onChange={() => set("execution_mode", mode)}
                      className="sr-only"
                    />
                    <span
                      className={`grid size-8 shrink-0 place-items-center rounded-full bg-white/8 ${tint}`}
                    >
                      <Icon aria-hidden className="size-4" />
                    </span>
                    <span className="min-w-0">
                      <span className={`block text-sm font-semibold ${checked ? tint : ""}`}>
                        {t(`mode.${mode}`)}
                      </span>
                      <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                        {t(`newProject.modeHelp.${mode}`)}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        </Group>

        {/* Budget. */}
        <Group title={t("newProject.budgetGroup")} footer={t("newProject.budgetHelp")}>
          <Row
            label={t("newProject.budget")}
            description={
              errors.budget ? (
                <FieldError id={`${id}-budget-error`} message={errors.budget} />
              ) : (
                estimateText
              )
            }
          >
            <AmountField
              label={t("newProject.budget")}
              value={form.budget}
              onChange={(value) => set("budget", value)}
              describedBy={errors.budget ? `${id}-budget-error` : undefined}
              decreaseLabel={t("budget.decrease")}
              increaseLabel={t("budget.increase")}
            />
          </Row>
        </Group>

        {/* Repository and delivery: optional, collapsed by default. */}
        <section className="space-y-1.5">
          <button
            type="button"
            aria-expanded={advanced}
            aria-controls={`${id}-advanced`}
            onClick={() => setAdvanced(!advanced)}
            className="flex w-full items-center gap-1.5 rounded-lg px-3 py-1 text-left text-[13px] font-semibold text-fg/85 hover:text-fg"
          >
            <ChevronRight
              aria-hidden
              className={`size-4 text-muted transition-transform duration-200 ${advanced ? "rotate-90" : ""}`}
            />
            {t("newProject.advanced")}
            <span className="ml-1 text-xs font-normal text-muted">{t("newProject.optional")}</span>
          </button>
          {advanced ? (
            <div id={`${id}-advanced`} className="os-pop">
              <Group footer={t("newProject.advancedHelp")}>
                <Row
                  label={t("newProject.repo")}
                  htmlFor={`${id}-repo`}
                  description={
                    <FieldError id={`${id}-repo-error`} message={errors.remote_repo_url} />
                  }
                >
                  <InlineInput
                    id={`${id}-repo`}
                    type="url"
                    mono
                    className="w-72"
                    placeholder="https://github.com/acme/app"
                    value={form.remote_repo_url ?? ""}
                    onChange={(e) => set("remote_repo_url", e.target.value)}
                  />
                </Row>
                <Row
                  label={t("newProject.token")}
                  htmlFor={`${id}-token`}
                  description={
                    errors.remote_token ? (
                      <FieldError id={`${id}-token-error`} message={errors.remote_token} />
                    ) : (
                      t("newProject.tokenHelp")
                    )
                  }
                >
                  <InlineInput
                    id={`${id}-token`}
                    type="password"
                    mono
                    className="w-72"
                    autoComplete="off"
                    value={form.remote_token ?? ""}
                    onChange={(e) => set("remote_token", e.target.value)}
                  />
                </Row>
                <Row label={t("newProject.delivery")} htmlFor={`${id}-delivery`}>
                  <InlineSelect
                    id={`${id}-delivery`}
                    value={form.delivery_mode}
                    onChange={(e) =>
                      set("delivery_mode", e.target.value as NewProject["delivery_mode"])
                    }
                  >
                    <option value="pull_request">{t("delivery.pull_request")}</option>
                    <option value="push_main">{t("delivery.push_main")}</option>
                  </InlineSelect>
                </Row>
                <Row label={t("newProject.residency")} htmlFor={`${id}-residency`}>
                  <InlineSelect
                    id={`${id}-residency`}
                    value={form.data_residency}
                    onChange={(e) =>
                      set("data_residency", e.target.value as NewProject["data_residency"])
                    }
                  >
                    <option value="any">{t("residency.any")}</option>
                    <option value="local">{t("residency.local")}</option>
                  </InlineSelect>
                </Row>
              </Group>
            </div>
          ) : null}
        </section>
      </div>

      {/* Action bar pinned to the bottom of the window. */}
      <div className="sticky bottom-0 -mx-5 -mb-5 flex flex-wrap items-center gap-2 border-t border-line bg-[rgb(24_24_32/0.72)] px-5 py-3 backdrop-blur-xl">
        <p className="mr-auto min-w-0 truncate text-xs text-muted">
          {t(`mode.${form.execution_mode}`)} · {eur(parseAmount(form.budget) ?? 0, 0)}
        </p>
        <Button
          size="sm"
          className="rounded-full px-4"
          onClick={() => submit(false)()}
          disabled={save.isPending}
        >
          {t("newProject.saveDraft")}
        </Button>
        <Button
          size="sm"
          type="submit"
          variant="primary"
          className="rounded-full px-4"
          icon={<Play aria-hidden className="size-3.5" />}
          busy={save.isPending}
        >
          {t("newProject.start")}
        </Button>
      </div>
    </form>
  );
}
