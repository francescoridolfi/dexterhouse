// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client.ts";
import { api } from "../../api/endpoints.ts";
import { keys, useMe } from "../../api/queries.ts";
import type { ModelProfile } from "../../api/types.ts";
import { BudgetBar } from "../../components/Badges.tsx";
import { Bars } from "../../components/Bars.tsx";
import { Button } from "../../components/Button.tsx";
import {
  Card,
  ComingSoon,
  EmptyState,
  ErrorState,
  LoadingBlock,
} from "../../components/Feedback.tsx";
import { SelectField, TextField } from "../../components/Fields.tsx";
import { Tabs } from "../../components/Tabs.tsx";
import { toastError, toastSuccess } from "../../components/toastStore.ts";
import { can } from "../../utils/auth.ts";
import { dateTime, eur, integer } from "../../utils/format.ts";

const SECTIONS = ["organization", "members", "profiles", "providers", "budget", "tokens"] as const;

function OrganizationSection() {
  const { t } = useTranslation();
  const me = useMe();
  const client = useQueryClient();
  const org = useQuery({ queryKey: keys.organization, queryFn: api.organization });
  const [name, setName] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api.updateOrganization({ name: name ?? "" }),
    onSuccess: () => {
      toastSuccess(t("settings.saved"));
      void client.invalidateQueries({ queryKey: keys.organization });
      void client.invalidateQueries({ queryKey: keys.me });
    },
    onError: (error) => toastError(t("settings.saveFailed"), error),
  });
  if (org.isPending) return <LoadingBlock />;
  if (org.isError) return <ErrorState error={org.error} onRetry={() => void org.refetch()} />;
  const owner = can(me.data, "owner");
  return (
    <Card title={t("settings.section.organization")}>
      <form
        className="max-w-md space-y-3 p-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <TextField
          label={t("settings.orgName")}
          value={name ?? org.data.name}
          disabled={!owner}
          onChange={(e) => setName(e.target.value)}
        />
        <p className="text-sm text-muted">{t("settings.slug", { slug: org.data.slug })}</p>
        {owner ? (
          <Button type="submit" variant="primary" busy={save.isPending} disabled={name === null}>
            {t("save")}
          </Button>
        ) : null}
      </form>
    </Card>
  );
}

function MembersSection() {
  const { t } = useTranslation();
  const members = useQuery({ queryKey: keys.members, queryFn: api.members });
  if (members.isPending) return <LoadingBlock />;
  if (members.isError)
    return <ErrorState error={members.error} onRetry={() => void members.refetch()} />;
  return (
    <div className="space-y-4">
      <Card title={t("settings.section.members")}>
        <ul className="divide-y divide-line">
          {members.data.results.map((m) => (
            <li key={m.id} className="flex justify-between px-4 py-2 text-sm">
              <span>{m.user.username}</span>
              <span className="text-muted">{t(`roles.${m.role}`)}</span>
            </li>
          ))}
        </ul>
      </Card>
      <ComingSoon title={t("settings.inviteSoon")} />
    </div>
  );
}

function ProfileCard({
  profile,
  providers,
  admin,
}: {
  profile: ModelProfile;
  providers: string[];
  admin: boolean;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [form, setForm] = useState({
    provider: profile.provider ?? "",
    model: profile.model ?? "",
    base_url: profile.base_url,
    api_key_env: profile.configured ? (profile.api_key_env ?? "") : "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () =>
      api.saveModelProfile(profile.profile, { ...form, is_local: form.provider === "ollama" }),
    onSuccess: () => {
      setErrors({});
      toastSuccess(t("settings.saved"));
      void client.invalidateQueries({ queryKey: keys.profiles });
    },
    onError: (error) => {
      if (error instanceof ApiError) setErrors(error.fieldErrors());
      toastError(t("settings.saveFailed"), error);
    },
  });
  const missing = !profile.provider || (profile.needs_key && !profile.api_key);
  return (
    <Card
      title={profile.profile}
      className={missing && profile.profile === "strong" ? "border-blocked" : ""}
    >
      <form
        className="space-y-3 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {missing && profile.profile === "strong" ? (
          <p role="alert" className="text-sm text-blocked">
            {t("settings.strongMissing")}
          </p>
        ) : null}
        <p className="text-xs text-muted">
          {t("settings.source", { source: t(`settings.sourceName.${profile.source ?? "none"}`) })}
          {profile.is_local ? ` · ${t("settings.local")}` : ""}
        </p>
        <SelectField
          label={t("settings.provider")}
          value={form.provider}
          disabled={!admin}
          onChange={(e) => setForm({ ...form, provider: e.target.value })}
        >
          <option value="">—</option>
          {providers.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </SelectField>
        <TextField
          label={t("settings.model")}
          value={form.model}
          disabled={!admin}
          error={errors.model}
          onChange={(e) => setForm({ ...form, model: e.target.value })}
        />
        <TextField
          label={t("settings.baseUrl")}
          value={form.base_url}
          disabled={!admin}
          onChange={(e) => setForm({ ...form, base_url: e.target.value })}
        />
        <TextField
          label={t("settings.keyEnv")}
          value={form.api_key_env}
          placeholder={profile.api_key_env ?? ""}
          disabled={!admin}
          error={errors.api_key_env ?? errors.options}
          hint={t("settings.keyState", {
            state: profile.api_key ? t("settings.keySet") : t("settings.keyMissing"),
          })}
          onChange={(e) => setForm({ ...form, api_key_env: e.target.value })}
        />
        <div className="flex gap-2">
          {admin ? (
            <Button
              type="submit"
              variant="primary"
              busy={save.isPending}
              disabled={!form.provider || !form.model}
            >
              {t("save")}
            </Button>
          ) : null}
          <Button disabled title={t("comingSoon")}>
            {t("settings.test")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ProfilesSection() {
  const me = useMe();
  const profiles = useQuery({ queryKey: keys.profiles, queryFn: api.modelProfiles });
  const providers = useQuery({ queryKey: keys.providers, queryFn: api.providers });
  if (profiles.isPending) return <LoadingBlock rows={4} />;
  if (profiles.isError)
    return <ErrorState error={profiles.error} onRetry={() => void profiles.refetch()} />;
  const names = (providers.data?.results ?? []).map((p) => p.id);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {profiles.data.results.map((profile) => (
        <ProfileCard
          key={`${profile.profile}-${profile.provider}-${profile.model}`}
          profile={profile}
          providers={names}
          admin={can(me.data, "admin")}
        />
      ))}
    </div>
  );
}

function ProvidersSection() {
  const { t } = useTranslation();
  const providers = useQuery({ queryKey: keys.providers, queryFn: api.providers });
  if (providers.isPending) return <LoadingBlock />;
  if (providers.isError)
    return <ErrorState error={providers.error} onRetry={() => void providers.refetch()} />;
  return (
    <Card title={t("settings.section.providers")}>
      <ul className="divide-y divide-line">
        {providers.data.results.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
            <span className="font-mono font-medium">{p.id}</span>
            {p.local ? (
              <span className="rounded-full border border-line px-2 text-xs">
                {t("settings.local")}
              </span>
            ) : null}
            <span className="ml-auto text-muted">
              {p.needs_key
                ? p.key_set
                  ? t("settings.keySet")
                  : t("settings.keyMissing")
                : t("settings.noKey")}
              {p.binary_found !== undefined
                ? ` · ${p.binary_found ? t("settings.cliFound") : t("settings.cliMissing")}`
                : ""}
              {p.base_url ? ` · ${p.base_url}` : ""}
            </span>
            {p.id === "anthropic-cli" ? (
              <p className="w-full text-xs text-muted">{t("settings.cliTerms")}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function BudgetSection() {
  const { t } = useTranslation();
  const me = useMe();
  const client = useQueryClient();
  const budget = useQuery({ queryKey: keys.orgBudget, queryFn: api.orgBudget, retry: false });
  const usage = useQuery({
    queryKey: keys.orgUsage(budget.data?.month ?? ""),
    queryFn: () => api.orgUsage(budget.data?.month),
    enabled: !!budget.data,
  });
  const [value, setValue] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api.setOrgBudget(value === "" ? null : value),
    onSuccess: () => {
      toastSuccess(t("settings.saved"));
      setValue(null);
      void client.invalidateQueries({ queryKey: ["organization"] });
      void client.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error) => toastError(t("settings.saveFailed"), error),
  });
  if (budget.isPending) return <LoadingBlock />;
  if (budget.isError) {
    if (budget.error instanceof ApiError && budget.error.status === 403)
      return <EmptyState title={t("settings.adminOnly")} />;
    return <ErrorState error={budget.error} onRetry={() => void budget.refetch()} />;
  }
  const b = budget.data;
  return (
    <div className="space-y-4">
      <Card title={t("settings.monthlyBudget", { month: b.month })}>
        <div className="space-y-3 p-4">
          {b.budget_monthly !== null ? (
            <BudgetBar spent={b.spent_month} budget={b.budget_monthly} />
          ) : (
            <p className="text-sm">{t("settings.unlimited", { spent: eur(b.spent_month) })}</p>
          )}
          {can(me.data, "admin") ? (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                save.mutate();
              }}
            >
              <TextField
                label={t("settings.budgetMonthly")}
                type="number"
                min="0"
                step="1"
                value={value ?? (b.budget_monthly ? String(Number(b.budget_monthly)) : "")}
                hint={t("settings.emptyUnlimited")}
                onChange={(e) => setValue(e.target.value)}
              />
              <Button
                type="submit"
                variant="primary"
                busy={save.isPending}
                disabled={value === null}
              >
                {t("save")}
              </Button>
            </form>
          ) : null}
        </div>
      </Card>
      {usage.data ? (
        <Card title={t("settings.usage")}>
          <div className="grid gap-4 p-4 md:grid-cols-2">
            <dl className="grid grid-cols-2 gap-1 text-sm">
              <dt className="text-muted">{t("settings.spent")}</dt>
              <dd>{eur(usage.data.spent)}</dd>
              <dt className="text-muted">{t("settings.calls")}</dt>
              <dd>{integer(usage.data.calls)}</dd>
              <dt className="text-muted">{t("settings.tokens")}</dt>
              <dd>{integer(usage.data.tokens.input + usage.data.tokens.output)}</dd>
            </dl>
            <Bars
              label={t("settings.byProject")}
              bars={usage.data.projects.map((p) => ({
                key: p.project_id,
                label: p.name,
                value: Number(p.cost),
                display: eur(p.cost),
              }))}
            />
          </div>
          <p className="px-4 pb-3 text-xs text-muted">
            {t("settings.updated", { when: dateTime(new Date().toISOString()) })}
          </p>
        </Card>
      ) : null}
    </div>
  );
}

export function SettingsPage() {
  const { t } = useTranslation();
  const { section = "organization" } = useParams();
  const navigate = useNavigate();
  const active = (SECTIONS as readonly string[]).includes(section) ? section : "organization";
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <h1 className="text-2xl font-semibold">{t("settings.title")}</h1>
      <Tabs
        label={t("settings.title")}
        idPrefix="settings"
        tabs={SECTIONS.map((id) => ({ id, label: t(`settings.section.${id}`) }))}
        active={active}
        onChange={(id) => void navigate(`/settings/${id}`)}
      />
      <div role="tabpanel" id={`settings-panel-${active}`} aria-labelledby={`settings-${active}`}>
        {active === "organization" ? <OrganizationSection /> : null}
        {active === "members" ? <MembersSection /> : null}
        {active === "profiles" ? <ProfilesSection /> : null}
        {active === "providers" ? <ProvidersSection /> : null}
        {active === "budget" ? <BudgetSection /> : null}
        {active === "tokens" ? <ComingSoon title={t("settings.tokensSoon")} /> : null}
      </div>
    </div>
  );
}
