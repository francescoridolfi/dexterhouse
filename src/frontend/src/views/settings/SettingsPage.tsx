// SPDX-License-Identifier: AGPL-3.0-or-later
// Settings, after macOS System Settings: a sidebar of tinted icons (the liquid tabs in narrow
// windows) and inset grouped lists on the right.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Check,
  KeyRound,
  type LucideIcon,
  Plug,
  Sparkles,
  TriangleAlert,
  Users,
  Wallet,
} from "lucide-react";
import { type FormEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client.ts";
import { api } from "../../api/endpoints.ts";
import { keys, useMe } from "../../api/queries.ts";
import type { ModelProfile, OrgBudget, Role } from "../../api/types.ts";
import { AmountField } from "../../components/AmountField.tsx";
import { BudgetBar } from "../../components/Badges.tsx";
import { Bars } from "../../components/Bars.tsx";
import { Button } from "../../components/Button.tsx";
import { EmptyState, ErrorState, LoadingBlock } from "../../components/Feedback.tsx";
import { Tabs } from "../../components/Tabs.tsx";
import { toastError, toastSuccess } from "../../components/toastStore.ts";
import { formatAmount, parseAmount } from "../../utils/amount.ts";
import { can } from "../../utils/auth.ts";
import { dateTime, eur, integer } from "../../utils/format.ts";
import {
  Group,
  InlineInput,
  InlineSelect,
  Monogram,
  Pill,
  Row,
  SaveBar,
  SectionHeader,
  Switch,
  type Tone,
} from "./parts.tsx";

const SECTIONS = ["organization", "members", "profiles", "providers", "budget", "tokens"] as const;
type Section = (typeof SECTIONS)[number];

const ICONS: Record<Section, { icon: LucideIcon; tint: [string, string] }> = {
  organization: { icon: Building2, tint: ["#5e9bff", "#2c4fe0"] },
  members: { icon: Users, tint: ["#48d597", "#0f9c62"] },
  profiles: { icon: Sparkles, tint: ["#c08cff", "#7039e0"] },
  providers: { icon: Plug, tint: ["#ffb340", "#f06a1d"] },
  budget: { icon: Wallet, tint: ["#5ee0e0", "#1b8fa8"] },
  tokens: { icon: KeyRound, tint: ["#a1a1aa", "#52525b"] },
};

function SectionIcon({ section, size = "size-6" }: { section: Section; size?: string }) {
  const { icon: Icon, tint } = ICONS[section];
  return (
    <span
      aria-hidden
      className={`grid ${size} shrink-0 place-items-center rounded-[7px] shadow-[inset_0_1px_0_rgb(255_255_255/0.35),0_1px_2px_rgb(0_0_0/0.4)]`}
      style={{ background: `linear-gradient(160deg, ${tint[0]}, ${tint[1]})` }}
    >
      <Icon className="size-3.5 text-white" strokeWidth={2.2} />
    </span>
  );
}

function initials(text: string): string {
  const parts = text.split(/[\s._-]+/).filter(Boolean);
  return (parts.length > 1 ? parts.map((p) => p[0]).join("") : text.slice(0, 2))
    .slice(0, 2)
    .toUpperCase();
}

// --- Organization ------------------------------------------------------------------------

function OrganizationSection() {
  const { t } = useTranslation();
  const me = useMe();
  const client = useQueryClient();
  const nameId = useId();
  const org = useQuery({ queryKey: keys.organization, queryFn: api.organization });
  const [name, setName] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api.updateOrganization({ name: name ?? "" }),
    onSuccess: () => {
      toastSuccess(t("settings.saved"));
      setName(null);
      void client.invalidateQueries({ queryKey: keys.organization });
      void client.invalidateQueries({ queryKey: keys.me });
    },
    onError: (error) => toastError(t("settings.saveFailed"), error),
  });
  if (org.isPending) return <LoadingBlock />;
  if (org.isError) return <ErrorState error={org.error} onRetry={() => void org.refetch()} />;
  const owner = can(me.data, "owner");
  const role = me.data?.organizations[0]?.role;
  const dirty = name !== null && name.trim() !== org.data.name;
  return (
    <form
      className="space-y-3"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        if (dirty) save.mutate();
      }}
    >
      <Group footer={owner ? null : t("settings.ownerOnly")}>
        <Row label={t("settings.orgName")} htmlFor={nameId}>
          <InlineInput
            id={nameId}
            value={name ?? org.data.name}
            disabled={!owner}
            onChange={(e) => setName(e.target.value)}
          />
        </Row>
        <Row label={t("settings.slugLabel")} description={t("settings.slugHelp")}>
          <span className="font-mono text-[13px] text-muted">{org.data.slug}</span>
        </Row>
        {role ? (
          <Row label={t("settings.yourRole")}>
            <Pill tone={ROLE_TONE[role]}>{t(`roles.${role}`)}</Pill>
          </Row>
        ) : null}
      </Group>
      <SaveBar
        dirty={dirty}
        busy={save.isPending}
        disabled={!name?.trim()}
        onDiscard={() => setName(null)}
      />
    </form>
  );
}

// --- Members -------------------------------------------------------------------------------

const ROLE_TONE: Record<Role, Tone> = {
  owner: "info",
  admin: "ok",
  member: "idle",
  viewer: "idle",
};

function MembersSection() {
  const { t } = useTranslation();
  const me = useMe();
  const members = useQuery({ queryKey: keys.members, queryFn: api.members });
  if (members.isPending) return <LoadingBlock />;
  if (members.isError)
    return <ErrorState error={members.error} onRetry={() => void members.refetch()} />;
  return (
    <div className="space-y-6">
      <Group
        title={t("settings.membersCount", { count: members.data.results.length })}
        footer={t("settings.inviteSoon")}
      >
        {members.data.results.map((m) => (
          <Row
            key={m.id}
            icon={<Monogram text={initials(m.user.username)} seed={m.user.username} round />}
            label={
              <span className="flex items-center gap-2">
                {m.user.username}
                {m.user.username === me.data?.username ? (
                  <Pill tone="info">{t("settings.you")}</Pill>
                ) : null}
              </span>
            }
            description={t("settings.memberSince", { date: dateTime(m.created_at) })}
          >
            <Pill tone={ROLE_TONE[m.role]}>{t(`roles.${m.role}`)}</Pill>
          </Row>
        ))}
        <Row label={t("settings.invite")} description={t("comingSoon")}>
          <Button size="sm" className="rounded-full px-3.5" disabled>
            {t("settings.invite")}…
          </Button>
        </Row>
      </Group>
    </div>
  );
}

// --- Model profiles ------------------------------------------------------------------------

function profileTone(profile: ModelProfile): { tone: Tone; label: string } {
  const missing = !profile.provider || (profile.needs_key && !profile.api_key);
  if (!profile.configured) return { tone: "idle", label: "settings.notConfigured" };
  if (missing)
    return { tone: profile.profile === "strong" ? "error" : "warn", label: "settings.keyAbsent" };
  return { tone: "ok", label: "settings.configured" };
}

function ProfileGroup({
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
  const id = useId();
  const initial = {
    provider: profile.provider ?? "",
    model: profile.model ?? "",
    base_url: profile.base_url,
    api_key_env: profile.configured ? (profile.api_key_env ?? "") : "",
  };
  const [form, setForm] = useState(initial);
  const initialTerms = profile.options.acknowledge_cli_terms === true;
  const [terms, setTerms] = useState(initialTerms);
  const cli = form.provider === "anthropic-cli";
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({
    // The PUT replaces the options: keep the ones already set (temperature, max_tokens…).
    mutationFn: () =>
      api.saveModelProfile(profile.profile, {
        ...form,
        is_local: form.provider === "ollama",
        options: { ...profile.options, ...(cli ? { acknowledge_cli_terms: terms } : {}) },
      }),
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
  const dirty =
    (Object.keys(initial) as (keyof typeof initial)[]).some((k) => form[k] !== initial[k]) ||
    (cli && terms !== initialTerms);
  const status = profileTone(profile);
  const strongMissing = profile.profile === "strong" && status.tone === "error";
  const set = (key: keyof typeof initial) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <Group
        title={<span className="capitalize">{profile.profile}</span>}
        aside={
          <span className="flex gap-1.5">
            {profile.is_local ? <Pill tone="info">{t("settings.local")}</Pill> : null}
            <Pill tone={status.tone}>
              {status.tone === "ok" ? <Check aria-hidden className="size-3" /> : null}
              {t(status.label)}
            </Pill>
          </span>
        }
        footer={
          <>
            {t(`settings.profileHelp.${profile.profile}`, { defaultValue: "" })}{" "}
            {t("settings.source", {
              source: t(`settings.sourceName.${profile.source ?? "none"}`),
            })}
          </>
        }
      >
        {strongMissing ? (
          <div
            role="alert"
            className="flex items-center gap-2 bg-failed/10 px-4 py-2.5 text-sm text-failed"
          >
            <TriangleAlert aria-hidden className="size-4 shrink-0" />
            {t("settings.strongMissing")}
          </div>
        ) : null}
        <Row label={t("settings.provider")} htmlFor={`${id}-provider`}>
          <InlineSelect
            id={`${id}-provider`}
            value={form.provider}
            disabled={!admin}
            onChange={set("provider")}
          >
            <option value="">—</option>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </InlineSelect>
        </Row>
        {cli ? (
          <Row label={t("settings.cliAccept")} description={t("settings.cliTerms")}>
            <Switch
              checked={terms}
              disabled={!admin}
              label={t("settings.cliAccept")}
              onChange={setTerms}
            />
          </Row>
        ) : null}
        <Row
          label={t("settings.model")}
          htmlFor={`${id}-model`}
          description={errors.model ? <span className="text-failed">{errors.model}</span> : null}
        >
          <InlineInput
            id={`${id}-model`}
            mono
            value={form.model}
            disabled={!admin}
            aria-invalid={!!errors.model || undefined}
            onChange={set("model")}
          />
        </Row>
        <Row label={t("settings.baseUrl")} htmlFor={`${id}-url`}>
          <InlineInput
            id={`${id}-url`}
            mono
            value={form.base_url}
            placeholder={t("settings.baseUrlDefault")}
            disabled={!admin}
            onChange={set("base_url")}
          />
        </Row>
        {profile.needs_key || form.api_key_env ? (
          <Row
            label={t("settings.keyEnv")}
            htmlFor={`${id}-key`}
            description={
              errors.api_key_env || errors.options ? (
                <span className="text-failed">{errors.api_key_env ?? errors.options}</span>
              ) : (
                t("settings.keyHelp")
              )
            }
          >
            <InlineInput
              id={`${id}-key`}
              mono
              className="w-44"
              value={form.api_key_env}
              placeholder={profile.api_key_env ?? "ANTHROPIC_API_KEY"}
              disabled={!admin}
              onChange={set("api_key_env")}
            />
            <Pill tone={profile.api_key ? "ok" : "error"}>
              {profile.api_key ? t("settings.keyPresent") : t("settings.keyAbsent")}
            </Pill>
          </Row>
        ) : null}
        <Row label={t("settings.test")} description={t("comingSoon")}>
          <Button size="sm" className="rounded-full px-3.5" disabled>
            {t("settings.test")}
          </Button>
        </Row>
      </Group>
      {admin ? (
        <SaveBar
          dirty={dirty}
          busy={save.isPending}
          disabled={!form.provider || !form.model || (cli && !terms)}
          onDiscard={() => {
            setForm(initial);
            setTerms(initialTerms);
          }}
        />
      ) : null}
    </form>
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
    <div className="space-y-7">
      {profiles.data.results.map((profile) => (
        <ProfileGroup
          key={`${profile.profile}-${profile.provider}-${profile.model}`}
          profile={profile}
          providers={names}
          admin={can(me.data, "admin")}
        />
      ))}
    </div>
  );
}

// --- Providers -----------------------------------------------------------------------------

function ProvidersSection() {
  const { t } = useTranslation();
  const providers = useQuery({ queryKey: keys.providers, queryFn: api.providers });
  if (providers.isPending) return <LoadingBlock />;
  if (providers.isError)
    return <ErrorState error={providers.error} onRetry={() => void providers.refetch()} />;
  return (
    <Group footer={t("settings.providersHelp")}>
      {providers.data.results.map((p) => {
        const description = [
          p.base_url,
          p.id === "anthropic-cli" ? t("settings.cliTerms") : null,
        ].filter(Boolean);
        return (
          <Row
            key={p.id}
            icon={<Monogram text={initials(p.id)} seed={p.id} />}
            label={<span className="font-mono text-[13px]">{p.id}</span>}
            description={
              description.length ? (
                <span className="font-mono break-all">{description.join(" · ")}</span>
              ) : undefined
            }
          >
            {p.local ? <Pill tone="info">{t("settings.local")}</Pill> : null}
            {p.binary_found !== undefined ? (
              <Pill tone={p.binary_found ? "ok" : "error"}>
                {p.binary_found ? t("settings.cliFound") : t("settings.cliMissing")}
              </Pill>
            ) : null}
            {p.needs_key ? (
              <Pill tone={p.key_set ? "ok" : "error"}>
                {p.key_set ? t("settings.keyPresent") : t("settings.keyAbsent")}
              </Pill>
            ) : (
              <Pill tone="idle">{t("settings.noKey")}</Pill>
            )}
          </Row>
        );
      })}
    </Group>
  );
}

// --- Budget --------------------------------------------------------------------------------

function BudgetForm({ budget }: { budget: OrgBudget }) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const me = useMe();
  const admin = can(me.data, "admin");
  const initialLimit = budget.budget_monthly === null ? null : Number(budget.budget_monthly);
  const [unlimited, setUnlimited] = useState(initialLimit === null);
  const [value, setValue] = useState(
    initialLimit === null ? "" : formatAmount(initialLimit, i18n.language),
  );
  const amount = parseAmount(value);
  const next = unlimited ? null : amount;
  const dirty = next !== initialLimit;
  const invalid = !unlimited && amount === null;
  const reset = () => {
    setUnlimited(initialLimit === null);
    setValue(initialLimit === null ? "" : formatAmount(initialLimit, i18n.language));
  };
  const save = useMutation({
    mutationFn: () => api.setOrgBudget(next === null ? null : String(next)),
    onSuccess: () => {
      toastSuccess(t("settings.saved"));
      void client.invalidateQueries({ queryKey: ["organization"] });
      void client.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error) => toastError(t("settings.saveFailed"), error),
  });
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (dirty && !invalid) save.mutate();
      }}
    >
      <Group
        title={t("settings.monthlyBudget", { month: budget.month })}
        footer={t("settings.limitHelp")}
      >
        <div className="px-4 py-4 [&>div]:w-full">
          {budget.budget_monthly !== null ? (
            <BudgetBar spent={budget.spent_month} budget={budget.budget_monthly} />
          ) : (
            <p className="text-sm">{t("settings.unlimited", { spent: eur(budget.spent_month) })}</p>
          )}
        </div>
        <Row label={t("settings.unlimitedLabel")} description={t("settings.unlimitedHelp")}>
          <Switch
            checked={unlimited}
            disabled={!admin}
            label={t("settings.unlimitedLabel")}
            onChange={(on) => {
              setUnlimited(on);
              if (!on && !value) setValue(formatAmount(100, i18n.language));
            }}
          />
        </Row>
        {!unlimited ? (
          <Row label={t("settings.monthlyLimit")}>
            <AmountField
              label={t("settings.monthlyLimit")}
              value={value}
              onChange={setValue}
              step={10}
              disabled={!admin}
              decreaseLabel={t("settings.decrease")}
              increaseLabel={t("settings.increase")}
            />
          </Row>
        ) : null}
      </Group>
      {admin ? (
        <SaveBar dirty={dirty} busy={save.isPending} disabled={invalid} onDiscard={reset} />
      ) : null}
    </form>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-4 py-3.5">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 text-xl font-semibold tracking-tight tabular-nums">{value}</p>
    </div>
  );
}

function BudgetSection() {
  const { t } = useTranslation();
  const budget = useQuery({ queryKey: keys.orgBudget, queryFn: api.orgBudget, retry: false });
  const usage = useQuery({
    queryKey: keys.orgUsage(budget.data?.month ?? ""),
    queryFn: () => api.orgUsage(budget.data?.month),
    enabled: !!budget.data,
  });
  if (budget.isPending) return <LoadingBlock />;
  if (budget.isError) {
    if (budget.error instanceof ApiError && budget.error.status === 403)
      return <EmptyState title={t("settings.adminOnly")} />;
    return <ErrorState error={budget.error} onRetry={() => void budget.refetch()} />;
  }
  const u = usage.data;
  return (
    <div className="space-y-7">
      <BudgetForm key={`${budget.data.budget_monthly}`} budget={budget.data} />
      {u ? (
        <>
          <Group
            title={t("settings.usage")}
            footer={t("settings.updated", { when: dateTime(new Date().toISOString()) })}
          >
            <div className="grid grid-cols-1 divide-line @md:grid-cols-3 @md:divide-x @max-md:divide-y">
              <Stat label={t("settings.spent")} value={eur(u.spent)} />
              <Stat label={t("settings.calls")} value={integer(u.calls)} />
              <Stat
                label={t("settings.tokens")}
                value={integer(u.tokens.input + u.tokens.output)}
              />
            </div>
          </Group>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-7 @3xl:grid-cols-2">
            <Group title={t("settings.byProject")}>
              <div className="p-4">
                <Bars
                  label={t("settings.byProject")}
                  bars={u.projects.map((p) => ({
                    key: p.project_id,
                    label: p.name,
                    value: Number(p.cost),
                    display: eur(p.cost),
                  }))}
                />
              </div>
            </Group>
            <Group title={t("settings.byDay")}>
              <div className="p-4">
                <Bars
                  label={t("settings.byDay")}
                  bars={u.by_day.map((d) => ({
                    key: d.day,
                    label: d.day,
                    value: Number(d.cost),
                    display: eur(d.cost),
                  }))}
                />
              </div>
            </Group>
          </div>
        </>
      ) : null}
    </div>
  );
}

// --- Tokens --------------------------------------------------------------------------------

function TokensSection() {
  const { t } = useTranslation();
  return (
    <Group>
      <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
        <SectionIcon section="tokens" size="size-12" />
        <p className="font-medium">{t("settings.tokensSoon")}</p>
        <p className="max-w-sm text-sm text-muted">{t("settings.tokensDetail")}</p>
        <Pill tone="idle">{t("comingSoon")}</Pill>
      </div>
    </Group>
  );
}

// --- Page ----------------------------------------------------------------------------------

function Sidebar({ active }: { active: Section }) {
  const { t } = useTranslation();
  const me = useMe();
  const org = me.data?.organizations[0];
  return (
    <nav aria-label={t("settings.title")} className="hidden w-56 shrink-0 @3xl:block">
      {org ? (
        <div className="mb-3 flex items-center gap-3 rounded-[14px] bg-white/5 px-3 py-2.5">
          <Monogram text={initials(org.name)} seed={org.slug} />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{org.name}</p>
            <p className="truncate text-xs text-muted">
              {me.data?.display_name} · {t(`roles.${org.role}`)}
            </p>
          </div>
        </div>
      ) : null}
      <ul className="space-y-0.5">
        {SECTIONS.map((id) => {
          const selected = id === active;
          return (
            <li key={id}>
              <Link
                to={`/settings/${id}`}
                aria-current={selected ? "page" : undefined}
                className={`flex h-8 items-center gap-2.5 rounded-[8px] px-2 text-[13px] transition-colors ${
                  selected
                    ? "bg-accent text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.2)]"
                    : "text-fg/90 hover:bg-white/6"
                }`}
              >
                <SectionIcon section={id} />
                {t(`settings.section.${id}`)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function SettingsPage() {
  const { t } = useTranslation();
  const { section = "organization" } = useParams();
  const navigate = useNavigate();
  const active: Section = (SECTIONS as readonly string[]).includes(section)
    ? (section as Section)
    : "organization";
  return (
    <div className="mx-auto flex max-w-5xl gap-8 pt-2">
      <Sidebar active={active} />
      <div className="min-w-0 flex-1">
        <div className="mb-5 flex justify-center @3xl:hidden">
          <Tabs
            label={t("settings.title")}
            idPrefix="settings"
            tabs={SECTIONS.map((id) => ({ id, label: t(`settings.section.${id}`) }))}
            active={active}
            onChange={(id) => void navigate(`/settings/${id}`)}
          />
        </div>
        <div
          role="region"
          id={`settings-panel-${active}`}
          aria-labelledby={`settings-title-${active}`}
          className="max-w-3xl"
        >
          <div id={`settings-title-${active}`}>
            <SectionHeader
              title={t(`settings.section.${active}`)}
              description={t(`settings.help.${active}`)}
            />
          </div>
          {active === "organization" ? <OrganizationSection /> : null}
          {active === "members" ? <MembersSection /> : null}
          {active === "profiles" ? <ProfilesSection /> : null}
          {active === "providers" ? <ProvidersSection /> : null}
          {active === "budget" ? <BudgetSection /> : null}
          {active === "tokens" ? <TokensSection /> : null}
        </div>
      </div>
    </div>
  );
}
