// SPDX-License-Identifier: AGPL-3.0-or-later
// Building blocks of the Settings app, after macOS System Settings: inset grouped lists with
// the label on the left and the control on the right, a switch, and a save bar that appears
// only while something changed.
import { type ReactNode, type SelectHTMLAttributes, useId } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/Button.tsx";

export function Group({
  title,
  footer,
  aside,
  children,
}: {
  title?: ReactNode;
  footer?: ReactNode;
  /** Right side of the title line (a status pill). */
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-1.5">
      {title || aside ? (
        <div className="flex items-end gap-2 px-3">
          {title ? <h3 className="text-[13px] font-semibold text-fg/85">{title}</h3> : null}
          {aside ? <div className="ml-auto">{aside}</div> : null}
        </div>
      ) : null}
      <div className="overflow-hidden rounded-[14px] border border-line bg-white/4 shadow-[inset_0_1px_0_rgb(255_255_255/0.05)]">
        <div className="divide-y divide-line">{children}</div>
      </div>
      {footer ? <div className="px-3 text-xs leading-relaxed text-muted">{footer}</div> : null}
    </section>
  );
}

/** One row of a group. `htmlFor` ties the label to the control on the right. */
export function Row({
  label,
  description,
  htmlFor,
  icon,
  children,
}: {
  label: ReactNode;
  description?: ReactNode;
  htmlFor?: string;
  icon?: ReactNode;
  children?: ReactNode;
}) {
  const Label = htmlFor ? "label" : "div";
  return (
    <div className="flex min-h-12 flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
      {icon}
      <div className="min-w-0 flex-1">
        <Label htmlFor={htmlFor} className="block text-sm">
          {label}
        </Label>
        {description ? (
          <div className="mt-0.5 text-xs leading-relaxed text-muted">{description}</div>
        ) : null}
      </div>
      {children !== undefined ? (
        <div className="flex max-w-full min-w-0 items-center gap-2">{children}</div>
      ) : null}
    </div>
  );
}

const FIELD =
  "h-8 rounded-[9px] border border-white/8 bg-black/25 px-2.5 text-sm text-fg shadow-[inset_0_1px_2px_rgb(0_0_0/0.25)] placeholder:text-muted/70 focus:border-accent/60 focus:ring-3 focus:ring-accent/25 focus:outline-none disabled:opacity-50";

export function InlineInput({
  id,
  mono = false,
  className = "w-56",
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & { mono?: boolean }) {
  return (
    <input
      id={id}
      autoComplete="off"
      className={`${FIELD} max-w-full ${mono ? "font-mono text-[13px]" : ""} ${className}`}
      {...rest}
    />
  );
}

export function InlineSelect({
  children,
  className = "w-56",
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className={`relative inline-flex max-w-full ${className}`}>
      <select className={`${FIELD} w-full appearance-none pr-8`} {...rest}>
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-muted"
      />
    </span>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-10 shrink-0 rounded-full transition-colors duration-200 disabled:opacity-50 ${
        checked ? "bg-[#30d158]" : "bg-white/15"
      } shadow-[inset_0_1px_2px_rgb(0_0_0/0.3)]`}
    >
      <span
        aria-hidden
        className={`absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow-[0_2px_4px_rgb(0_0_0/0.35)] transition-transform duration-300 ease-(--ease-spring) ${
          checked ? "translate-x-4" : ""
        }`}
      />
    </button>
  );
}

export type Tone = "ok" | "warn" | "error" | "idle" | "info";

const TONES: Record<Tone, string> = {
  ok: "bg-done/15 text-done",
  warn: "bg-blocked/15 text-blocked",
  error: "bg-failed/15 text-failed",
  idle: "bg-white/8 text-muted",
  info: "bg-accent/15 text-accent",
};

export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex h-5 items-center gap-1 rounded-full px-2 text-[11px] font-medium whitespace-nowrap ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

/** Monogram tile (members, providers): initials on a tinted gradient. */
export function Monogram({
  text,
  seed,
  round = false,
}: {
  text: string;
  seed: string;
  round?: boolean;
}) {
  const tints = [
    ["#5e9bff", "#2c4fe0"],
    ["#c08cff", "#7039e0"],
    ["#48d597", "#0f9c62"],
    ["#ffb340", "#f06a1d"],
    ["#ff6f91", "#d1305c"],
    ["#5ee0e0", "#1b8fa8"],
    ["#a1a1aa", "#52525b"],
  ] as const;
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  const [from, to] = tints[hash % tints.length] ?? tints[0];
  return (
    <span
      aria-hidden
      className={`grid size-8 shrink-0 place-items-center text-[11px] font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.35)] ${round ? "rounded-full" : "rounded-[9px]"}`}
      style={{ background: `linear-gradient(160deg, ${from}, ${to})` }}
    >
      {text}
    </span>
  );
}

/** Appears under a group while its form is dirty: discard on the left, save on the right. */
export function SaveBar({
  dirty,
  busy,
  disabled,
  onDiscard,
}: {
  dirty: boolean;
  busy?: boolean;
  disabled?: boolean;
  onDiscard: () => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  if (!dirty) return null;
  return (
    <div id={id} className="os-pop flex items-center justify-end gap-2 px-1">
      <Button size="sm" className="rounded-full px-3.5" onClick={onDiscard}>
        {t("cancel")}
      </Button>
      <Button
        size="sm"
        type="submit"
        variant="primary"
        className="rounded-full px-3.5"
        busy={busy}
        disabled={disabled}
      >
        {t("save")}
      </Button>
    </div>
  );
}

export function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <header className="mb-5">
      <h2 className="text-[22px] leading-tight font-semibold tracking-tight">{title}</h2>
      <p className="mt-1 max-w-prose text-sm text-muted">{description}</p>
    </header>
  );
}
