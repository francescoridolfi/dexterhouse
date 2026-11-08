// SPDX-License-Identifier: AGPL-3.0-or-later
// Shiki (VS Code TextMate grammars) with the JavaScript regex engine: no WASM, no eval, and
// tokens are rendered as React elements, so the strict CSP (style-src 'self') still holds.
// Loaded lazily: this module and every grammar are separate chunks.
import { createHighlighterCore, type HighlighterCore, type ThemedToken } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";

import type { Lang } from "./lang.ts";

export const THEME = "github-dark-default";

const LANGS: Record<Exclude<Lang, "text">, () => Promise<unknown>> = {
  typescript: () => import("shiki/langs/typescript.mjs"),
  tsx: () => import("shiki/langs/tsx.mjs"),
  javascript: () => import("shiki/langs/javascript.mjs"),
  jsx: () => import("shiki/langs/jsx.mjs"),
  json: () => import("shiki/langs/json.mjs"),
  python: () => import("shiki/langs/python.mjs"),
  shellscript: () => import("shiki/langs/shellscript.mjs"),
  sql: () => import("shiki/langs/sql.mjs"),
  yaml: () => import("shiki/langs/yaml.mjs"),
  markdown: () => import("shiki/langs/markdown.mjs"),
  css: () => import("shiki/langs/css.mjs"),
  html: () => import("shiki/langs/html.mjs"),
  diff: () => import("shiki/langs/diff.mjs"),
  docker: () => import("shiki/langs/docker.mjs"),
  go: () => import("shiki/langs/go.mjs"),
  rust: () => import("shiki/langs/rust.mjs"),
  java: () => import("shiki/langs/java.mjs"),
  toml: () => import("shiki/langs/toml.mjs"),
};

let core: Promise<HighlighterCore> | null = null;
const loaded = new Set<string>();

async function highlighter(): Promise<HighlighterCore> {
  core ??= createHighlighterCore({
    themes: [import("shiki/themes/github-dark-default.mjs")],
    langs: [],
    engine: createJavaScriptRegexEngine({ forgiving: true }),
  });
  return core;
}

/** Tokens for `code`; `null` for plain text (the caller keeps showing the raw lines). */
export async function tokenize(code: string, lang: Lang): Promise<ThemedToken[][] | null> {
  if (lang === "text") return null;
  const hl = await highlighter();
  if (!loaded.has(lang)) {
    await hl.loadLanguage(LANGS[lang]() as Parameters<HighlighterCore["loadLanguage"]>[0]);
    loaded.add(lang);
  }
  return hl.codeToTokensBase(code, { lang, theme: THEME });
}
