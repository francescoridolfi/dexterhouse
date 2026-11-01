// SPDX-License-Identifier: AGPL-3.0-or-later
// react-i18next: English default, complete Italian (CD-036). Strings written by agents are
// never translated. `?lng=pseudo` renders pseudo-localised text to spot hard-coded strings.
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.ts";
import it from "./it.ts";

export const LANGUAGES = ["en", "it"] as const;
export type Language = (typeof LANGUAGES)[number];
const KEY = "dh.language";

function initialLanguage(): string {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get("lng");
    if (fromUrl) return fromUrl;
    const saved = localStorage.getItem(KEY);
    if (saved) return saved;
  } catch {
    // fall through to the browser language
  }
  return navigator.language.startsWith("it") ? "it" : "en";
}

export function pseudo(value: string): string {
  const map: Record<string, string> = { a: "á", e: "é", i: "í", o: "ö", u: "ü", A: "Å", E: "É" };
  return `⟦${value.replace(/[aeiouAE]/g, (c) => map[c] ?? c)}⟧`;
}

void i18n.use(initReactI18next).init({
  resources: { en, it },
  lng: initialLanguage(),
  fallbackLng: "en",
  defaultNS: "common",
  ns: Object.keys(en),
  interpolation: { escapeValue: false },
  postProcess: initialLanguage() === "pseudo" ? ["pseudo"] : [],
});
i18n.use({ type: "postProcessor", name: "pseudo", process: (value: string) => pseudo(value) });

export function setLanguage(language: Language): void {
  try {
    localStorage.setItem(KEY, language);
  } catch {
    // not persisted
  }
  void i18n.changeLanguage(language);
  document.documentElement.lang = language;
}

export default i18n;
