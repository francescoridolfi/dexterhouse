// SPDX-License-Identifier: AGPL-3.0-or-later
// Code app sidebar: search by file name, then the folder tree (ARIA tree, arrow keys).
import { ChevronRight, File, Folder, FolderOpen } from "lucide-react";
import { type KeyboardEvent, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { CodeEntry } from "../../api/types.ts";
import { FilterBar, SearchField } from "../../components/FilterBar.tsx";
import { ancestors, buildTree, matchFiles, visibleRows } from "./treeModel.ts";

const ROW =
  "flex min-h-8 w-full items-center gap-1.5 rounded-[8px] pr-2 text-left text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-accent";

export function FileTree({
  entries,
  selected,
  onSelect,
}: {
  entries: CodeEntry[];
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const tree = useMemo(() => buildTree(entries), [entries]);
  const [open, setOpen] = useState<Set<string>>(() => new Set(ancestors(selected ?? "")));
  const list = useRef<HTMLUListElement>(null);

  // A deep link to another file opens its folders (adjusted while rendering, not in an effect).
  const [revealed, setRevealed] = useState(selected);
  if (revealed !== selected) {
    setRevealed(selected);
    const missing = ancestors(selected ?? "").filter((p) => !open.has(p));
    if (missing.length) setOpen(new Set([...open, ...missing]));
  }

  const hits = useMemo(() => matchFiles(entries, q), [entries, q]);
  const rows = useMemo(() => visibleRows(tree, open), [tree, open]);

  const toggle = (path: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const onKey = (event: KeyboardEvent<HTMLUListElement>) => {
    const items = [...(list.current?.querySelectorAll<HTMLElement>("[role=treeitem]") ?? [])];
    const index = items.indexOf(document.activeElement as HTMLElement);
    const move = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (move && index >= 0) {
      event.preventDefault();
      items[Math.max(0, Math.min(items.length - 1, index + move))]?.focus();
    }
  };

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <FilterBar>
        <SearchField label={t("codeApp.searchFiles")} value={q} onChange={setQ} />
      </FilterBar>
      {q.trim() ? (
        <ul aria-label={t("codeApp.results")} className="min-h-0 overflow-auto">
          {hits.length === 0 ? (
            <li className="px-3 py-4 text-sm text-muted">{t("codeApp.noMatch")}</li>
          ) : (
            hits.map((hit) => (
              <li key={hit.path}>
                <button
                  type="button"
                  onClick={() => onSelect(hit.path)}
                  aria-current={hit.path === selected || undefined}
                  className={`${ROW} flex-col items-start justify-center px-2.5 py-1 hover:bg-white/6 ${hit.path === selected ? "bg-accent/18" : ""}`}
                >
                  <span className="truncate font-medium">{hit.path.split("/").pop()}</span>
                  <span className="w-full truncate font-mono text-[11px] text-muted">
                    {hit.path}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      ) : (
        <ul
          ref={list}
          role="tree"
          aria-label={t("codeApp.files")}
          onKeyDown={onKey}
          className="min-h-0 overflow-auto"
        >
          {rows.map(({ node, depth }) => {
            const isOpen = open.has(node.path);
            const current = node.path === selected;
            const Icon = node.dir ? (isOpen ? FolderOpen : Folder) : File;
            return (
              <li
                key={node.path}
                role="treeitem"
                aria-level={depth + 1}
                aria-expanded={node.dir ? isOpen : undefined}
                aria-selected={current}
                tabIndex={current || (!selected && depth === 0) ? 0 : -1}
                onClick={() => (node.dir ? toggle(node.path) : onSelect(node.path))}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    if (node.dir) toggle(node.path);
                    else onSelect(node.path);
                  } else if (node.dir && event.key === "ArrowRight" && !isOpen) toggle(node.path);
                  else if (node.dir && event.key === "ArrowLeft" && isOpen) toggle(node.path);
                }}
                className={`${ROW} cursor-default hover:bg-white/6 ${current ? "bg-accent/18 text-fg" : ""}`}
                style={{ paddingLeft: 6 + depth * 14 }}
              >
                <ChevronRight
                  aria-hidden
                  className={`size-3.5 shrink-0 text-muted transition-transform ${node.dir ? "" : "invisible"} ${isOpen ? "rotate-90" : ""}`}
                />
                <Icon
                  aria-hidden
                  className={`size-3.5 shrink-0 ${node.dir ? "text-[#64d2ff]" : "text-muted"}`}
                />
                <span className="truncate">{node.name}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
