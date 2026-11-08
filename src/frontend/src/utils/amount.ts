// SPDX-License-Identifier: AGPL-3.0-or-later
// Euro amounts typed by people: "12,5", "12.50", "€ 12" → 12.5; null when not an amount.
export function parseAmount(raw: string): number | null {
  const text = raw.trim().replace(/\s|€/g, "").replace(",", ".");
  if (!/^\d+(\.\d{0,2})?$/.test(text)) return null;
  return Number(text);
}

export function formatAmount(value: number, language: string): string {
  return value.toLocaleString(language === "it" ? "it-IT" : "en-GB", {
    maximumFractionDigits: 2,
    useGrouping: false,
  });
}
