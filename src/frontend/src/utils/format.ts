// SPDX-License-Identifier: AGPL-3.0-or-later
// Numbers and dates with Intl in the UI language (ux_2d_states.md).
import i18n from "../i18n/index.ts";

const locale = () => (i18n.language === "it" ? "it-IT" : "en-GB");

export function eur(value: string | number | null | undefined, digits = 2): string {
  const n = Number(value ?? 0);
  return new Intl.NumberFormat(locale(), {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: digits,
    maximumFractionDigits: Math.max(digits, n !== 0 && Math.abs(n) < 0.01 ? 4 : digits),
  }).format(Number.isFinite(n) ? n : 0);
}

export function integer(value: number): string {
  return new Intl.NumberFormat(locale()).format(value);
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale(), { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

export function time(value: string): string {
  return new Intl.DateTimeFormat(locale(), {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "";
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function relative(value: string, now: number = Date.now()): string {
  const diff = (Date.parse(value) - now) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86_400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86_400), "day");
}
