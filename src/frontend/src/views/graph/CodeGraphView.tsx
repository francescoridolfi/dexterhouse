// SPDX-License-Identifier: AGPL-3.0-or-later
// The `code_graph` artifact: search, node and edge kind filters, the force-directed canvas
// and the selected node with its neighbours. File and symbol nodes open in the Code app.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { FilterBar, FilterGroup, SearchField } from "../../components/FilterBar.tsx";
import { codeHref } from "../code/links.ts";
import { GraphCanvas } from "./GraphCanvas.tsx";
import {
  type CodeGraph,
  EDGE_KINDS,
  type GraphNode,
  NODE_KINDS,
  codeTarget,
  filterGraph,
  kindsOf,
  searchNodes,
} from "./graphModel.ts";
import { NodePanel } from "./NodePanel.tsx";
import { EDGE_COLORS } from "./paint.ts";

/** Above this many nodes the symbols start hidden (they are most of a big graph). */
const BIG = 1500;

function Chip({
  label,
  count,
  on,
  color,
  onToggle,
}: {
  label: string;
  count: number;
  on: boolean;
  color?: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onToggle}
      className={`inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] transition-colors ${
        on ? "bg-accent/18 text-fg hover:bg-accent/25" : "bg-white/6 text-muted hover:bg-white/10"
      }`}
    >
      {color ? (
        <span aria-hidden className="size-2 rounded-full" style={{ background: color }} />
      ) : null}
      {label}
      <span className="text-xs tabular-nums opacity-70">{count}</span>
    </button>
  );
}

function toggled(set: Set<string>, value: string): Set<string> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export function CodeGraphView({
  graph,
  projectId,
  fill = false,
}: {
  graph: CodeGraph;
  projectId: string;
  /** Fill the parent's height (the Graph window) instead of a fixed-height canvas. */
  fill?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const nodeKinds = useMemo(
    () =>
      kindsOf(
        graph.nodes.map((n) => n.kind),
        NODE_KINDS,
      ),
    [graph],
  );
  const edgeKinds = useMemo(
    () =>
      kindsOf(
        graph.edges.map((e) => e.kind),
        EDGE_KINDS,
      ),
    [graph],
  );
  const [shownNodes, setShownNodes] = useState(
    () => new Set(nodeKinds.filter((k) => graph.nodes.length <= BIG || k !== "symbol")),
  );
  const [shownEdges, setShownEdges] = useState(() => new Set(edgeKinds));
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ id: string; seq: number } | null>(null);

  const visible = useMemo(
    () => filterGraph(graph, shownNodes, shownEdges),
    [graph, shownNodes, shownEdges],
  );
  const hits = useMemo(() => searchNodes(visible.nodes, q), [visible.nodes, q]);
  const matches = useMemo(() => new Set(hits.map((n) => n.id)), [hits]);
  const count = (values: { kind: string }[], kind: string) =>
    values.filter((v) => v.kind === kind).length;

  const select = (id: string | null, center = false) => {
    setSelected(id);
    if (id && center) setFocus((f) => ({ id, seq: (f?.seq ?? 0) + 1 }));
  };
  const open = (node: GraphNode) => {
    const target = codeTarget(node);
    if (target) void navigate(codeHref(projectId, { ...target, ref: graph.commit }));
    else select(node.id);
  };
  const current = graph.nodes.find((n) => n.id === selected) ?? null;

  return (
    <div className={`flex flex-col gap-3 ${fill ? "h-full min-h-0" : ""}`}>
      <FilterBar>
        <SearchField label={t("graph.search")} value={q} onChange={setQ} />
        <FilterGroup>
          {nodeKinds.map((k) => (
            <Chip
              key={k}
              label={t(`graph.node.${k}`, { defaultValue: k })}
              count={count(graph.nodes, k)}
              on={shownNodes.has(k)}
              onToggle={() => setShownNodes(toggled(shownNodes, k))}
            />
          ))}
        </FilterGroup>
      </FilterBar>
      <div role="group" aria-label={t("graph.edgeKinds")} className="flex flex-wrap gap-1.5">
        {edgeKinds.map((k) => (
          <Chip
            key={k}
            label={t(`graph.edge.${k}`, { defaultValue: k })}
            count={count(graph.edges, k)}
            color={EDGE_COLORS[k] ?? "#8e8e93"}
            on={shownEdges.has(k)}
            onToggle={() => setShownEdges(toggled(shownEdges, k))}
          />
        ))}
      </div>
      {q.trim() ? (
        <ul
          aria-label={t("graph.results")}
          className="flex max-h-28 flex-wrap gap-1.5 overflow-auto"
        >
          {hits.length === 0 ? (
            <li className="text-sm text-muted">{t("graph.noMatch")}</li>
          ) : (
            hits.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => select(n.id, true)}
                  className="h-7 rounded-full bg-white/8 px-2.5 font-mono text-xs hover:bg-white/14"
                >
                  {n.label}
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
      <div
        className={`grid grid-cols-[minmax(0,1fr)] gap-3 @3xl:grid-cols-[minmax(0,1fr)_17rem] ${fill ? "min-h-0 flex-1" : ""}`}
      >
        <GraphCanvas
          nodes={visible.nodes}
          edges={visible.edges}
          selected={selected}
          matches={matches}
          focus={focus}
          onSelect={(id) => select(id)}
          onOpen={open}
          className={fill ? "h-full min-h-80" : "h-[26rem]"}
        />
        <NodePanel graph={graph} node={current} onSelect={(id) => select(id, true)} onOpen={open} />
      </div>
    </div>
  );
}
