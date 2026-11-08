// SPDX-License-Identifier: AGPL-3.0-or-later
// Markdown written by agents (untrusted): raw HTML is never rendered (react-markdown default),
// links get a safe URL transform and open in a new tab, remote images are shown as links only
// (no tracking pixels; the CSP blocks them anyway). Fenced code goes through CodeBlock.
import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { CodeBlock } from "./CodeBlock.tsx";

const components: Components = {
  h1: (props) => (
    <h1 className="mt-6 mb-3 text-2xl font-semibold tracking-tight first:mt-0" {...props} />
  ),
  h2: (props) => (
    <h2
      className="mt-7 mb-2.5 border-b border-line pb-1.5 text-lg font-semibold tracking-tight first:mt-0"
      {...props}
    />
  ),
  h3: (props) => <h3 className="mt-5 mb-2 text-base font-semibold first:mt-0" {...props} />,
  h4: (props) => (
    <h4 className="mt-4 mb-1.5 text-sm font-semibold text-muted uppercase" {...props} />
  ),
  p: (props) => <p className="my-3 leading-relaxed first:mt-0 last:mb-0" {...props} />,
  ul: ({ className, ...props }) => (
    <ul
      className={`my-3 space-y-1 pl-5 ${className?.includes("contains-task-list") ? "list-none pl-1" : "list-disc"} marker:text-muted`}
      {...props}
    />
  ),
  ol: (props) => <ol className="my-3 list-decimal space-y-1 pl-5 marker:text-muted" {...props} />,
  li: (props) => (
    <li className="leading-relaxed [&>input]:mr-2 [&>input]:align-middle" {...props} />
  ),
  a: ({ href, ...props }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="text-accent underline-offset-2 hover:underline"
      {...props}
    />
  ),
  img: ({ src, alt }) => (
    <a
      href={typeof src === "string" ? src : undefined}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="text-accent underline-offset-2 hover:underline"
    >
      🖼 {alt || (typeof src === "string" ? src : "")}
    </a>
  ),
  blockquote: (props) => (
    <blockquote
      className="my-3 rounded-r-[10px] border-l-3 border-accent/60 bg-accent/6 py-1.5 pr-3 pl-4 text-fg/85"
      {...props}
    />
  ),
  hr: () => <hr className="my-6 border-line" />,
  table: (props) => (
    <div className="my-4 overflow-x-auto rounded-[12px] border border-line">
      <table className="w-full text-sm" {...props} />
    </div>
  ),
  thead: (props) => <thead className="bg-white/5 text-left text-xs text-muted" {...props} />,
  tbody: (props) => <tbody className="divide-y divide-line" {...props} />,
  tr: (props) => <tr className="even:bg-white/2" {...props} />,
  th: (props) => <th className="px-3 py-2 font-semibold" {...props} />,
  td: (props) => <td className="px-3 py-2 align-top" {...props} />,
  strong: (props) => <strong className="font-semibold text-fg" {...props} />,
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children, ...props }: ComponentPropsWithoutRef<"code">) => {
    const fence = /language-([\w+-]+)/.exec(className ?? "")?.[1];
    // react-markdown passes the code text as a string (or an array of strings).
    const text = (Array.isArray(children) ? children : [children])
      .filter((part): part is string => typeof part === "string")
      .join("");
    // Fenced blocks carry a language class or span lines; everything else is inline code.
    if (fence || text.includes("\n"))
      return (
        <div className="my-4">
          <CodeBlock code={text} lang={fence} />
        </div>
      );
    return (
      <code
        className="rounded-[6px] bg-white/8 px-1.5 py-0.5 font-mono text-[0.86em] text-[#ffa657]"
        {...props}
      >
        {children}
      </code>
    );
  },
};

export function Markdown({ source }: { source: string }) {
  return (
    <div className="max-w-[72ch] text-[14.5px] text-fg/90">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {source}
      </ReactMarkdown>
    </div>
  );
}
