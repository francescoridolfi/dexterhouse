// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client.ts";
import { api, type NewProject } from "../../api/endpoints.ts";
import { keys, useMeta } from "../../api/queries.ts";
import { Button } from "../../components/Button.tsx";
import { SelectField, TextArea, TextField } from "../../components/Fields.tsx";
import { toastError } from "../../components/toastStore.ts";
import { eur } from "../../utils/format.ts";

const BRIEF_MAX = 20_000;

/** Flow F1: one page, "save draft" or "start" (target < 60 s, NFR-U1). */
export function NewProjectPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const meta = useMeta();
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
  const estimate = useQuery({
    queryKey: keys.estimate(form.process ?? "", Math.round(form.brief.length / 500) * 500),
    queryFn: () => api.estimate(form.process ?? "software-house-default", form.brief.length),
    staleTime: 60_000,
  });

  const save = useMutation({
    mutationFn: async (start: boolean) => {
      const body = {
        ...form,
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
      if (error instanceof ApiError) setErrors(error.fieldErrors());
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

  return (
    <form onSubmit={submit(true)} className="mx-auto max-w-3xl space-y-5">
      <div className="flex items-center gap-3">
        <Link to="/projects" className="text-sm text-muted hover:text-fg">
          ← {t("nav.projects")}
        </Link>
        <h1 className="text-2xl font-semibold">{t("newProject.title")}</h1>
      </div>
      {summary ? (
        <div role="alert" className="rounded-card border border-failed p-3 text-sm text-failed">
          {t("newProject.fixErrors", { count: Object.keys(errors).length })}
        </div>
      ) : null}
      <TextField
        label={t("newProject.name")}
        value={form.name}
        maxLength={120}
        required
        error={errors.name}
        onChange={(e) => set("name", e.target.value)}
      />
      <TextArea
        label={t("newProject.brief")}
        rows={10}
        value={form.brief}
        maxLength={BRIEF_MAX}
        required
        error={errors.brief}
        hint={t("newProject.briefCount", { count: form.brief.length, max: BRIEF_MAX })}
        onChange={(e) => set("brief", e.target.value)}
      />
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label={t("newProject.process")}
          value={form.process}
          error={errors.process}
          onChange={(e) => set("process", e.target.value)}
        >
          {(meta.data?.processes ?? [{ name: "software-house-default" }]).map((p) => (
            <option key={p.name} value={p.name}>
              {t(`process.${p.name}`, { defaultValue: p.name })}
            </option>
          ))}
        </SelectField>
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">{t("newProject.mode")}</legend>
          <div className="flex gap-2">
            {(["supervised", "autonomous"] as const).map((mode) => (
              <label
                key={mode}
                className={`flex min-h-11 flex-1 cursor-pointer items-center justify-center rounded-card border px-3 text-sm ${form.execution_mode === mode ? "border-accent font-semibold text-accent" : "border-line"}`}
              >
                <input
                  type="radio"
                  name="mode"
                  value={mode}
                  checked={form.execution_mode === mode}
                  onChange={() => set("execution_mode", mode)}
                  className="sr-only"
                />
                {t(`mode.${mode}`)}
              </label>
            ))}
          </div>
          <p className="text-xs text-muted">{t(`mode.${form.execution_mode}Help`)}</p>
        </fieldset>
      </div>
      <TextField
        label={t("newProject.budget")}
        type="number"
        min="0"
        step="0.5"
        value={form.budget}
        required
        error={errors.budget}
        hint={
          estimate.data
            ? t("newProject.estimate", {
                low: eur(estimate.data.low, 0),
                high: eur(estimate.data.high, 0),
                basis: t(`estimate.${estimate.data.basis}`),
              })
            : undefined
        }
        onChange={(e) => set("budget", e.target.value)}
      />
      <button
        type="button"
        className="text-sm text-accent underline"
        aria-expanded={advanced}
        onClick={() => setAdvanced(!advanced)}
      >
        {t("newProject.advanced")}
      </button>
      {advanced ? (
        <div className="grid gap-4 rounded-card border border-line p-4 md:grid-cols-2">
          <TextField
            label={t("newProject.repo")}
            type="url"
            placeholder="https://github.com/acme/app"
            value={form.remote_repo_url ?? ""}
            error={errors.remote_repo_url}
            onChange={(e) => set("remote_repo_url", e.target.value)}
          />
          <TextField
            label={t("newProject.token")}
            type="password"
            autoComplete="off"
            hint={t("newProject.tokenHelp")}
            value={form.remote_token ?? ""}
            error={errors.remote_token}
            onChange={(e) => set("remote_token", e.target.value)}
          />
          <SelectField
            label={t("newProject.delivery")}
            value={form.delivery_mode}
            onChange={(e) => set("delivery_mode", e.target.value as NewProject["delivery_mode"])}
          >
            <option value="pull_request">{t("delivery.pull_request")}</option>
            <option value="push_main">{t("delivery.push_main")}</option>
          </SelectField>
          <SelectField
            label={t("newProject.residency")}
            value={form.data_residency}
            onChange={(e) => set("data_residency", e.target.value as NewProject["data_residency"])}
          >
            <option value="any">{t("residency.any")}</option>
            <option value="local">{t("residency.local")}</option>
          </SelectField>
        </div>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        <Button onClick={() => submit(false)()} disabled={save.isPending}>
          {t("newProject.saveDraft")}
        </Button>
        <Button type="submit" variant="primary" busy={save.isPending}>
          {t("newProject.start")}
        </Button>
      </div>
    </form>
  );
}
