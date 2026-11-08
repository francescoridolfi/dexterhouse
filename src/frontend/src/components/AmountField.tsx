// SPDX-License-Identifier: AGPL-3.0-or-later
// Euro amount in a recessed capsule (− € amount +): text input (accepts "12,5"), no browser
// spinner, one focus ring on the whole capsule, red ring while the text is not an amount.
import { Minus, Plus } from "lucide-react";
import { type InputHTMLAttributes, useId } from "react";
import { useTranslation } from "react-i18next";

import { formatAmount, parseAmount } from "../utils/amount.ts";

export function AmountField({
  label,
  value,
  onChange,
  step = 1,
  disabled = false,
  describedBy,
  decreaseLabel,
  increaseLabel,
  inputProps,
}: {
  /** Accessible name of the input (visually hidden). */
  label: string;
  value: string;
  onChange: (value: string) => void;
  step?: number;
  disabled?: boolean;
  describedBy?: string;
  decreaseLabel: string;
  increaseLabel: string;
  inputProps?: InputHTMLAttributes<HTMLInputElement>;
}) {
  const { i18n } = useTranslation();
  const id = useId();
  const amount = parseAmount(value);
  const valid = amount !== null || value.trim() === "";
  const nudge = (delta: number) =>
    onChange(
      formatAmount(Math.max(0, Math.round(((amount ?? 0) + delta) / step) * step), i18n.language),
    );
  const round =
    "grid size-7 shrink-0 place-items-center rounded-full text-muted transition-colors hover:bg-white/10 hover:text-fg disabled:opacity-40 disabled:hover:bg-transparent";
  return (
    <div
      className={`inline-flex h-8 items-center rounded-full bg-black/30 p-0.5 shadow-[inset_0_1px_2px_rgb(0_0_0/0.35)] ring-1 transition-shadow focus-within:ring-2 ${
        valid ? "ring-white/8 focus-within:ring-accent/70" : "ring-failed/70"
      } ${disabled ? "opacity-50" : ""}`}
    >
      <button
        type="button"
        aria-label={decreaseLabel}
        onClick={() => nudge(-step)}
        disabled={disabled || (amount ?? 0) <= 0}
        className={round}
      >
        <Minus aria-hidden className="size-3.5" />
      </button>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <span aria-hidden className="pl-1.5 text-sm text-muted">
        €
      </span>
      <input
        id={id}
        inputMode="decimal"
        autoComplete="off"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onFocus={(e) => e.currentTarget.select()}
        aria-invalid={!valid || undefined}
        aria-describedby={describedBy}
        className="w-16 bg-transparent px-1 text-center font-mono text-sm tabular-nums outline-none focus-visible:outline-none"
        {...inputProps}
      />
      <button
        type="button"
        aria-label={increaseLabel}
        onClick={() => nudge(step)}
        disabled={disabled}
        className={round}
      >
        <Plus aria-hidden className="size-3.5" />
      </button>
    </div>
  );
}
