// SPDX-License-Identifier: AGPL-3.0-or-later
// Read-only code view, editor-like: line numbers, language label, copy. The raw text shows at
// once; Shiki tokens replace it when the (lazy) grammar is ready.
import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ThemedToken } from "shiki/core";

import { type Lang, langFor } from "./lang.ts";

const ITALIC = 1;
const BOLD = 2;
const UNDERLINE = 4;

function tokenStyle(token: ThemedToken): React.CSSProperties {
  const style = token.fontStyle ?? 0;
  return {
    color: token.color,
    fontStyle: style & ITALIC ? "italic" : undefined,
    fontWeight: style & BOLD ? 600 : undefined,
    textDecoration: style & UNDERLINE ? "underline" : undefined,
  };
}

const LABELS: Partial<Record<Lang, string>> = {
  typescript: "TypeScript",
  tsx: "TSX",
  javascript: "JavaScript",
  jsx: "JSX",
  json: "JSON",
  python: "Python",
  shellscript: "Shell",
  sql: "SQL",
  yaml: "YAML",
  markdown: "Markdown",
  css: "CSS",
  html: "HTML",
  diff: "Diff",
  docker: "Dockerfile",
  go: "Go",
  rust: "Rust",
  java: "Java",
  toml: "TOML",
  text: "Text",
};

export function CodeBlock({
  code,
  lang: hint,
  title,
  maxHeight = "max-h-[60vh]",
}: {
  code: string;
  /** Fence tag or file name. */
  lang?: string;
  /** Shown in the header instead of the language (e.g. the file name). */
  title?: string;
  maxHeight?: string;
}) {
  const { t } = useTranslation();
  const lang = langFor(hint);
  const text = code.replace(/\n$/, "");
  const [result, setResult] = useState<{ key: string; tokens: ThemedToken[][] } | null>(null);
  const [copied, setCopied] = useState(false);
  const key = `${lang}\u0000${text}`;

  useEffect(() => {
    let alive = true;
    import("./highlighter.ts")
      .then(({ tokenize }) => tokenize(text, lang))
      .then((tokens) => {
        if (alive && tokens) setResult({ key, tokens });
      })
      .catch(() => undefined); // keep the plain text
    return () => {
      alive = false;
    };
  }, [key, lang, text]);

  const copy = () => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };

  const tokens = result?.key === key ? result.tokens : null;
  const lines = tokens ?? text.split("\n");
  const gutter = String(lines.length).length;

  return (
    <figure className="overflow-hidden rounded-[14px] border border-white/8 bg-[#0d1117]/90 shadow-[inset_0_1px_0_rgb(255_255_255/0.05)]">
      <figcaption className="flex h-8 items-center gap-2 border-b border-white/6 bg-white/3 pr-1.5 pl-3 text-[11px] text-muted">
        <span className="truncate font-mono">{title ?? LABELS[lang] ?? lang}</span>
        <button
          type="button"
          onClick={copy}
          aria-label={copied ? t("code.copied") : t("code.copy")}
          title={copied ? t("code.copied") : t("code.copy")}
          className="ml-auto grid size-6 place-items-center rounded-md hover:bg-white/10 hover:text-fg"
        >
          {copied ? (
            <Check aria-hidden className="size-3.5 text-done" />
          ) : (
            <Copy aria-hidden className="size-3.5" />
          )}
        </button>
      </figcaption>
      <pre
        className={`${maxHeight} overflow-auto py-2.5 font-mono text-[12.5px] leading-[1.6] text-[#e6edf3]`}
      >
        <code className="grid min-w-max">
          {lines.map((line, index) => (
            <span key={index} className="flex hover:bg-white/4">
              <span
                aria-hidden
                className="sticky left-0 shrink-0 bg-[#0d1117] pr-4 pl-3 text-right text-white/25 select-none"
                style={{ width: `${gutter + 3}ch` }}
              >
                {index + 1}
              </span>
              <span className="pr-4 whitespace-pre">
                {typeof line === "string"
                  ? line || " "
                  : line.length === 0
                    ? " "
                    : line.map((token, i) => (
                        <span key={i} style={tokenStyle(token)}>
                          {token.content}
                        </span>
                      ))}
              </span>
            </span>
          ))}
        </code>
      </pre>
    </figure>
  );
}
