// SPDX-License-Identifier: AGPL-3.0-or-later
// Language detection for CodeBlock (kept apart from Shiki so the main bundle stays small).
export const LANG_IDS = [
  "typescript",
  "tsx",
  "javascript",
  "jsx",
  "json",
  "python",
  "shellscript",
  "sql",
  "yaml",
  "markdown",
  "css",
  "html",
  "diff",
  "docker",
  "go",
  "rust",
  "java",
  "toml",
] as const;

export type Lang = (typeof LANG_IDS)[number] | "text";

const ALIASES: Record<string, Lang> = {
  ts: "typescript",
  mts: "typescript",
  cts: "typescript",
  js: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  sh: "shellscript",
  bash: "shellscript",
  zsh: "shellscript",
  shell: "shellscript",
  console: "shellscript",
  yml: "yaml",
  md: "markdown",
  htm: "html",
  patch: "diff",
  dockerfile: "docker",
  rs: "rust",
  jsonc: "json",
};

/** Language from a fence tag or a file name (`api.ts`, `Dockerfile`); "text" when unknown. */
export function langFor(hint: string | undefined | null): Lang {
  if (!hint) return "text";
  const raw = hint.toLowerCase().trim();
  const base = raw.split("/").pop() ?? raw;
  if (base === "dockerfile" || base.startsWith("dockerfile.")) return "docker";
  const ext = base.includes(".") ? (base.split(".").pop() ?? "") : base;
  if ((LANG_IDS as readonly string[]).includes(ext)) return ext as Lang;
  return ALIASES[ext] ?? "text";
}
