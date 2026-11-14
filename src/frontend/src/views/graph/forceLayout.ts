// SPDX-License-Identifier: AGPL-3.0-or-later
// A small force-directed layout (the d3-force model, written here to add no dependency):
// springs on the edges, Barnes–Hut repulsion between all nodes (O(n log n)), a weak pull to
// the centre, and a cooling "alpha" so the layout settles. Pure math: no DOM, no styles.

export interface SimNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** Pinned position while the user drags the node. */
  fx: number | null;
  fy: number | null;
}

export interface SimLink {
  source: number;
  target: number;
}

const ALPHA_MIN = 0.001;
const ALPHA_DECAY = 1 - ALPHA_MIN ** (1 / 300);
const VELOCITY_DECAY = 0.4;
const THETA2 = 0.81; // Barnes–Hut accuracy (θ = 0.9)
const CHARGE = -60;
const DISTANCE = 42;
const GRAVITY = 0.04;

interface Quad {
  x0: number;
  y0: number;
  size: number;
  mass: number;
  cx: number;
  cy: number;
  /** A leaf holds one node index (or several at the same point). */
  points: number[] | null;
  kids: (Quad | null)[] | null;
}

function quad(x0: number, y0: number, size: number): Quad {
  return { x0, y0, size, mass: 0, cx: 0, cy: 0, points: null, kids: null };
}

function insert(q: Quad, nodes: SimNode[], i: number, depth = 0): void {
  const n = nodes[i]!;
  q.cx = (q.cx * q.mass + n.x) / (q.mass + 1);
  q.cy = (q.cy * q.mass + n.y) / (q.mass + 1);
  q.mass += 1;
  if (!q.kids) {
    if (!q.points || depth > 24) {
      (q.points ??= []).push(i);
      return;
    }
    const others = q.points;
    q.points = null;
    q.kids = [null, null, null, null];
    for (const j of others) place(q, nodes, j, depth);
  }
  place(q, nodes, i, depth);
}

function place(q: Quad, nodes: SimNode[], i: number, depth: number): void {
  const n = nodes[i]!;
  const half = q.size / 2;
  const right = n.x >= q.x0 + half ? 1 : 0;
  const bottom = n.y >= q.y0 + half ? 1 : 0;
  const k = bottom * 2 + right;
  q.kids![k] ??= quad(q.x0 + right * half, q.y0 + bottom * half, half);
  insert(q.kids![k], nodes, i, depth + 1);
}

function repel(q: Quad, n: SimNode, i: number, strength: number): void {
  if (q.mass === 0) return;
  const dx = q.cx - n.x;
  const dy = q.cy - n.y;
  let d2 = dx * dx + dy * dy;
  const far = q.size * q.size < THETA2 * d2;
  if (q.points?.includes(i)) {
    // Other nodes on the very same point: nudge apart, deterministically (no Math.random).
    if (q.points.length > 1) {
      const angle = i * 2.399963;
      n.vx += Math.cos(angle) * -strength * 0.05;
      n.vy += Math.sin(angle) * -strength * 0.05;
    }
    return;
  }
  if (far || q.points) {
    if (d2 < 1) d2 = 1;
    const f = (strength * q.mass) / d2;
    n.vx += dx * f;
    n.vy += dy * f;
    return;
  }
  if (q.kids) for (const kid of q.kids) if (kid) repel(kid, n, i, strength);
}

export class ForceLayout {
  readonly nodes: SimNode[];
  readonly links: SimLink[];
  alpha = 1;
  private readonly degree: number[];

  constructor(ids: string[], links: SimLink[]) {
    // Phyllotaxis seed (deterministic, already spread out).
    this.nodes = ids.map((id, i) => {
      const r = 10 * Math.sqrt(0.5 + i);
      const a = i * Math.PI * (3 - Math.sqrt(5));
      return { id, x: r * Math.cos(a), y: r * Math.sin(a), vx: 0, vy: 0, fx: null, fy: null };
    });
    this.links = links;
    this.degree = ids.map(() => 0);
    for (const l of links) {
      this.degree[l.source]! += 1;
      this.degree[l.target]! += 1;
    }
  }

  get settled(): boolean {
    return this.alpha < ALPHA_MIN;
  }

  reheat(alpha = 0.3): void {
    this.alpha = Math.max(this.alpha, alpha);
  }

  tick(): void {
    const { nodes, alpha } = this;
    if (nodes.length === 0) return;
    this.alpha += (0 - alpha) * ALPHA_DECAY;
    for (const l of this.links) {
      const s = nodes[l.source]!;
      const t = nodes[l.target]!;
      const dx = t.x + t.vx - s.x - s.vx || 1e-6;
      const dy = t.y + t.vy - s.y - s.vy || 1e-6;
      const d = Math.sqrt(dx * dx + dy * dy);
      const strength = 1 / Math.min(this.degree[l.source]!, this.degree[l.target]!);
      const f = ((d - DISTANCE) / d) * alpha * strength;
      const bias = this.degree[l.source]! / (this.degree[l.source]! + this.degree[l.target]!);
      t.vx -= dx * f * bias;
      t.vy -= dy * f * bias;
      s.vx += dx * f * (1 - bias);
      s.vy += dy * f * (1 - bias);
    }
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
    const root = quad(x0, y0, Math.max(x1 - x0, y1 - y0, 1) + 1);
    for (let i = 0; i < nodes.length; i += 1) insert(root, nodes, i);
    for (let i = 0; i < nodes.length; i += 1) {
      const n = nodes[i]!;
      repel(root, n, i, CHARGE * alpha);
      n.vx -= n.x * GRAVITY * alpha;
      n.vy -= n.y * GRAVITY * alpha;
    }
    for (const n of nodes) {
      if (n.fx !== null && n.fy !== null) {
        n.x = n.fx;
        n.y = n.fy;
        n.vx = 0;
        n.vy = 0;
        continue;
      }
      n.vx *= 1 - VELOCITY_DECAY;
      n.vy *= 1 - VELOCITY_DECAY;
      n.x += n.vx;
      n.y += n.vy;
    }
  }

  /** Run `n` ticks at once (reduced motion, tests). */
  run(n = 300): void {
    for (let i = 0; i < n && !this.settled; i += 1) this.tick();
  }

  /** Index of the node nearest to (x, y) within `radius`, or -1. */
  find(x: number, y: number, radius: number): number {
    let best = -1;
    let bestD = radius * radius;
    this.nodes.forEach((n, i) => {
      const d = (n.x - x) ** 2 + (n.y - y) ** 2;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    return best;
  }
}
