// SPDX-License-Identifier: AGPL-3.0-or-later
// The selected node: kind, location, community and its neighbours grouped by edge kind.
import { ArrowLeft, ArrowRight, CodeXml, MousePointerClick } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/Button.tsx";
import {
  type CodeGraph,
  type GraphNode,
  codeTarget,
  communityColor,
  neighbors,
} from "./graphModel.ts";

const MAX_NEIGHBORS = 60;

export function NodePanel({
  graph,
  node,
  onSelect,
  onOpen,
}: {
  graph: CodeGraph;
  node: GraphNode | null;
  onSelect: (id: string) => void;
  onOpen: (node: GraphNode) => void;
}) {
  const { t } = useTranslation();
  const list = useMemo(() => (node ? neighbors(graph, node.id) : []), [graph, node]);
  if (!node)
    return (
      <aside className="flex flex-col items-center justify-center gap-2 rounded-[14px] border border-line bg-surface p-4 text-center text-sm text-muted">
        <MousePointerClick aria-hidden className="size-6" />
        {t("graph.pickNode")}
      </aside>
    );
  const target = codeTarget(node);
  return (
    <aside
      aria-label={t("graph.selected")}
      className="min-h-0 space-y-3 overflow-auto rounded-[14px] border border-line bg-surface p-4"
    >
      <div>
        <p className="flex items-center gap-1.5 text-xs text-muted">
          <span
            aria-hidden
            className="size-2.5 rounded-full"
            style={{ background: communityColor(node.community) }}
          />
          {t(`graph.kindOne.${node.kind}`, { defaultValue: node.kind })}
          {node.symbolKind ? ` · ${node.symbolKind}` : ""}
          {node.community !== null ? ` · ${t("graph.community", { n: node.community })}` : ""}
        </p>
        <h3 className="mt-1 font-mono text-sm font-semibold break-all">{node.label}</h3>
        {node.path ? (
          <p className="mt-0.5 font-mono text-xs break-all text-muted">
            {node.path}
            {node.line ? `:${node.line}` : ""}
          </p>
        ) : null}
      </div>
      {target ? (
        <Button
          size="sm"
          variant="primary"
          className="w-full rounded-full"
          icon={<CodeXml aria-hidden className="size-3.5" />}
          onClick={() => onOpen(node)}
        >
          {t("graph.openInCode")}
        </Button>
      ) : null}
      <div>
        <p className="text-xs font-semibold tracking-wide text-muted uppercase">
          {t("graph.neighbors", { count: list.length })}
        </p>
        <ul className="mt-1">
          {list.slice(0, MAX_NEIGHBORS).map(({ node: other, kind, direction }, i) => {
            const Arrow = direction === "out" ? ArrowRight : ArrowLeft;
            return (
              <li key={`${other.id}-${kind}-${direction}-${i}`}>
                <button
                  type="button"
                  onClick={() => onSelect(other.id)}
                  className="flex min-h-8 w-full items-center gap-1.5 rounded-[8px] px-1.5 text-left text-[13px] hover:bg-white/6"
                >
                  <Arrow aria-hidden className="size-3 shrink-0 text-muted" />
                  <span className="shrink-0 text-xs text-muted">
                    {t(`graph.edge.${kind}`, { defaultValue: kind })}
                  </span>
                  <span className="truncate font-mono text-xs">{other.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
        {list.length > MAX_NEIGHBORS ? (
          <p className="mt-1 text-xs text-muted">
            {t("graph.more", { count: list.length - MAX_NEIGHBORS })}
          </p>
        ) : null}
      </div>
    </aside>
  );
}
