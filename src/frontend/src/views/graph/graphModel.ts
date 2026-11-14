// SPDX-License-Identifier: AGPL-3.0-or-later
// The `code_graph` artifact (schema 1): nodes are files, modules, symbols and externals;
// edges are imports, defines, calls, inherits and tests. Agent output is untrusted, so the
// parser keeps what is well formed, drops dangling edges and never throws.

/** Artifact kind of the dependency graph (core `ArtifactKind.CODE_GRAPH`). */
export const CODE_GRAPH_KIND = "code_graph";
export const NODE_KINDS = ["file", "module", "symbol", "external"] as const;
export const EDGE_KINDS = ["imports", "defines", "calls", "inherits", "tests"] as const;

export interface GraphNode {
  id: string;
  kind: string;
  label: string;
  path: string | null;
  lang: string | null;
  line: number | null;
  symbolKind: string | null;
  parent: string | null;
  community: number | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: string;
}

export interface CodeGraph {
  commit: string | null;
  generatedAt: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const str = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);
const int = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? Math.trunc(v) : null;

function node(raw: unknown): GraphNode | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const id = str(r.id) ?? (typeof r.id === "number" ? String(r.id) : null);
  if (!id) return null;
  const line = int(r.line);
  return {
    id,
    kind: str(r.kind) ?? "symbol",
    label: (str(r.label) ?? id).slice(0, 200),
    path: str(r.path),
    lang: str(r.lang),
    line: line !== null && line > 0 ? line : null,
    symbolKind: str(r.symbol_kind),
    parent: str(r.parent),
    community: int(r.community),
  };
}

const parsed = new WeakMap<object, CodeGraph | null>();

/**
 * The graph in `data`, or `null` when it is not a schema-1 code graph at all. Memoized per
 * `data` object, so a re-render (or a refetch with equal data) keeps the same graph and
 * the layout does not restart.
 */
export function parseCodeGraph(data: unknown): CodeGraph | null {
  if (!data || typeof data !== "object") return null;
  if (!parsed.has(data)) parsed.set(data, parse(data as Record<string, unknown>));
  return parsed.get(data) ?? null;
}

function parse(d: Record<string, unknown>): CodeGraph | null {
  if (!Array.isArray(d.nodes) || !Array.isArray(d.edges)) return null;
  if (d.schema !== undefined && d.schema !== 1) return null;
  const nodes = new Map<string, GraphNode>();
  for (const raw of d.nodes) {
    const n = node(raw);
    if (n && !nodes.has(n.id)) nodes.set(n.id, n);
  }
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();
  for (const raw of d.edges) {
    if (!raw || typeof raw !== "object") continue;
    const r = raw as Record<string, unknown>;
    const source = str(r.source) ?? (typeof r.source === "number" ? String(r.source) : null);
    const target = str(r.target) ?? (typeof r.target === "number" ? String(r.target) : null);
    const kind = str(r.kind) ?? "calls";
    if (!source || !target || !nodes.has(source) || !nodes.has(target)) continue;
    const key = `${source}\u0000${target}\u0000${kind}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({ source, target, kind });
  }
  return {
    commit: str(d.commit),
    generatedAt: str(d.generated_at),
    nodes: [...nodes.values()],
    edges,
  };
}

/** Known kinds first (contract order), then any other kind the producer used. */
export function kindsOf(values: string[], known: readonly string[]): string[] {
  const present = new Set(values);
  return [
    ...known.filter((k) => present.has(k)),
    ...[...present].filter((k) => !known.includes(k)).sort(),
  ];
}

/** A stable, well-spread colour per community (golden angle on the hue wheel). */
export function communityColor(community: number | null): string {
  if (community === null) return "hsl(220 8% 62%)";
  const hue = (((community * 137.508) % 360) + 360) % 360;
  return `hsl(${hue.toFixed(1)} 72% 62%)`;
}

export interface Neighbor {
  node: GraphNode;
  kind: string;
  direction: "in" | "out";
}

export function neighbors(graph: CodeGraph, id: string): Neighbor[] {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const out: Neighbor[] = [];
  for (const e of graph.edges) {
    if (e.source === id) out.push({ node: byId.get(e.target)!, kind: e.kind, direction: "out" });
    else if (e.target === id)
      out.push({ node: byId.get(e.source)!, kind: e.kind, direction: "in" });
  }
  return out;
}

/** Nodes of the enabled kinds, and the enabled edges between them. */
export function filterGraph(graph: CodeGraph, nodeKinds: Set<string>, edgeKinds: Set<string>) {
  const nodes = graph.nodes.filter((n) => nodeKinds.has(n.kind));
  const ids = new Set(nodes.map((n) => n.id));
  const edges = graph.edges.filter(
    (e) => edgeKinds.has(e.kind) && ids.has(e.source) && ids.has(e.target),
  );
  return { nodes, edges };
}

export function searchNodes(nodes: GraphNode[], query: string, limit = 30): GraphNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const score = (n: GraphNode) => {
    const label = n.label.toLowerCase();
    if (label === q) return 0;
    if (label.startsWith(q)) return 1;
    if (label.includes(q)) return 2;
    // Paths only for a query with a `/` (every node of `gymbook/` would match "book").
    return q.includes("/") && (n.path ?? "").toLowerCase().includes(q) ? 3 : 9;
  };
  return nodes
    .map((n) => [score(n), n] as const)
    .filter(([s]) => s < 9)
    .sort((a, b) => a[0] - b[0] || a[1].label.localeCompare(b[1].label))
    .slice(0, limit)
    .map(([, n]) => n);
}

/** File and symbol nodes with a path open in the Code app. */
export function codeTarget(n: GraphNode): { path: string; line: number | null } | null {
  if ((n.kind !== "file" && n.kind !== "symbol") || !n.path) return null;
  return { path: n.path, line: n.kind === "symbol" ? n.line : null };
}
