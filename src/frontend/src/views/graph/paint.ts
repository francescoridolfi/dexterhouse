// SPDX-License-Identifier: AGPL-3.0-or-later
// Drawing one frame of the code graph on a 2D canvas (colours are canvas state, not CSS).
import type { ForceLayout, SimNode } from "./forceLayout.ts";
import { type GraphEdge, type GraphNode, communityColor } from "./graphModel.ts";

export interface View {
  x: number;
  y: number;
  k: number;
}

export const RADIUS: Record<string, number> = { file: 6, module: 7, symbol: 3.5, external: 4.5 };
export const EDGE_COLORS: Record<string, string> = {
  imports: "#64d2ff",
  defines: "#8e8e93",
  calls: "#ffd60a",
  inherits: "#bf5af2",
  tests: "#30d158",
};
const FALLBACK_EDGE = "#8e8e93";
const SELECTED = "#ffffff";

/** The view that fits every node in a `w` x `h` box with a margin. */
export function fitTransform(nodes: SimNode[], w: number, h: number): View {
  if (nodes.length === 0 || w === 0) return { x: w / 2, y: h / 2, k: 1 };
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const n of nodes) {
    x0 = Math.min(x0, n.x);
    y0 = Math.min(y0, n.y);
    x1 = Math.max(x1, n.x);
    y1 = Math.max(y1, n.y);
  }
  // Room for the labels on the right; node sizes do not follow the zoom (see `paint`).
  const k = Math.min(
    6,
    Math.min((w - 160) / Math.max(x1 - x0, 1), (h - 48) / Math.max(y1 - y0, 1)),
  );
  const fit = Math.max(k, 0.05);
  return { k: fit, x: w / 2 - 40 - ((x0 + x1) / 2) * fit, y: h / 2 - ((y0 + y1) / 2) * fit };
}

interface Scene {
  layout: ForceLayout;
  nodes: GraphNode[];
  edges: GraphEdge[];
  selected: string | null;
  matches: Set<string>;
}

export function paint(
  ctx: CanvasRenderingContext2D,
  size: { w: number; h: number },
  view: View,
  { layout, nodes, edges, selected, matches }: Scene,
): void {
  const dpr = ctx.canvas.width / Math.max(size.w, 1);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, size.w, size.h);
  ctx.translate(view.x, view.y);
  ctx.scale(view.k, view.k);
  const at = new Map(layout.nodes.map((n) => [n.id, n]));
  const near = new Set<string>();
  if (selected) {
    near.add(selected);
    for (const e of edges) {
      if (e.source === selected) near.add(e.target);
      if (e.target === selected) near.add(e.source);
    }
  }
  const focusing = near.size > 0 || matches.size > 0;
  // Nodes grow a little with the zoom (x0.5-x1.5 on screen), never like the distances.
  const grow = Math.min(Math.max(view.k, 0.5), 1.5) / view.k;
  const lit = (id: string) => near.has(id) || matches.has(id);

  ctx.lineWidth = 1 / view.k;
  for (const e of edges) {
    const s = at.get(e.source);
    const t = at.get(e.target);
    if (!s || !t) continue;
    const on = selected !== null && (e.source === selected || e.target === selected);
    ctx.globalAlpha = on ? 0.95 : focusing ? 0.06 : 0.28;
    ctx.strokeStyle = EDGE_COLORS[e.kind] ?? FALLBACK_EDGE;
    ctx.lineWidth = (on ? 1.6 : 1) / view.k;
    ctx.beginPath();
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(t.x, t.y);
    ctx.stroke();
  }

  const labels: [GraphNode, SimNode, number][] = [];
  for (const node of nodes) {
    const p = at.get(node.id);
    if (!p) continue;
    const r = (RADIUS[node.kind] ?? 4) * grow;
    ctx.globalAlpha = focusing && !lit(node.id) ? 0.18 : 1;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    const color = communityColor(node.community);
    if (node.kind === "external") {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5 / Math.max(view.k, 0.5);
      ctx.stroke();
    } else {
      ctx.fillStyle = color;
      ctx.fill();
    }
    if (node.id === selected || matches.has(node.id)) {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = node.id === selected ? SELECTED : "#ffd60a";
      ctx.lineWidth = 2 / view.k;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 3 / view.k, 0, Math.PI * 2);
      ctx.stroke();
    }
    if (lit(node.id) || (view.k > 1.6 && node.kind !== "symbol") || view.k > 3)
      labels.push([node, p, r]);
  }

  ctx.globalAlpha = 1;
  ctx.font = `${11 / view.k}px Inter Variable, system-ui, sans-serif`;
  ctx.textBaseline = "middle";
  for (const [node, p, r] of labels.slice(0, 400)) {
    const x = p.x + r + 3 / view.k;
    ctx.lineWidth = 3 / view.k;
    ctx.strokeStyle = "rgb(11 13 18 / 0.85)";
    ctx.strokeText(node.label, x, p.y);
    ctx.fillStyle = node.id === selected ? SELECTED : "rgb(235 235 245 / 0.85)";
    ctx.fillText(node.label, x, p.y);
  }
}
