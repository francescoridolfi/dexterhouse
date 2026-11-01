// SPDX-License-Identifier: AGPL-3.0-or-later
// A* on the free cells of the floor grid: 8 neighbours, no corner cutting, octile distance.
import type { FloorGrid } from "../rooms/grid.ts";
import type { Cell } from "../rooms/plan.ts";

const SQRT2 = Math.SQRT2;
const STEPS: [number, number, number][] = [
  [1, 0, 1],
  [-1, 0, 1],
  [0, 1, 1],
  [0, -1, 1],
  [1, 1, SQRT2],
  [1, -1, SQRT2],
  [-1, 1, SQRT2],
  [-1, -1, SQRT2],
];

/** Binary min-heap of cell indices keyed by f score. */
class Heap {
  private items: number[] = [];
  private readonly score: Float64Array;
  constructor(score: Float64Array) {
    this.score = score;
  }
  get size() {
    return this.items.length;
  }
  push(index: number) {
    const items = this.items;
    items.push(index);
    let i = items.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (this.score[items[parent]!]! <= this.score[index]!) break;
      items[i] = items[parent]!;
      i = parent;
    }
    items[i] = index;
  }
  pop(): number {
    const items = this.items;
    const top = items[0]!;
    const last = items.pop()!;
    if (items.length > 0) {
      let i = 0;
      for (;;) {
        const left = 2 * i + 1;
        if (left >= items.length) break;
        const right = left + 1;
        const child =
          right < items.length && this.score[items[right]!]! < this.score[items[left]!]!
            ? right
            : left;
        if (this.score[items[child]!]! >= this.score[last]!) break;
        items[i] = items[child]!;
        i = child;
      }
      items[i] = last;
    }
    return top;
  }
}

function octile(ax: number, ay: number, bx: number, by: number): number {
  const dx = Math.abs(ax - bx);
  const dy = Math.abs(ay - by);
  return dx + dy + (SQRT2 - 2) * Math.min(dx, dy);
}

const free = (grid: FloorGrid, x: number, y: number) =>
  x >= 0 && y >= 0 && x < grid.w && y < grid.h && grid.blocked[y * grid.w + x] === 0;

/** Nearest free cell (breadth first), for avatars standing on a cell that became blocked. */
export function nearestFree(grid: FloorGrid, cell: Cell): Cell | null {
  const sx = Math.round(cell.x);
  const sy = Math.round(cell.y);
  for (let r = 0; r < Math.max(grid.w, grid.h); r++) {
    for (let dy = -r; dy <= r; dy++)
      for (let dx = -r; dx <= r; dx++) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
        if (free(grid, sx + dx, sy + dy)) return { x: sx + dx, y: sy + dy };
      }
  }
  return null;
}

/** Cells from `start` to `goal` included, or null when the goal cannot be reached. */
export function findPath(grid: FloorGrid, start: Cell, goal: Cell): Cell[] | null {
  const from = free(grid, start.x, start.y) ? start : nearestFree(grid, start);
  if (!from || !free(grid, goal.x, goal.y)) return null;
  const { w } = grid;
  const startIndex = from.y * w + from.x;
  const goalIndex = goal.y * w + goal.x;
  const cost = new Float64Array(grid.w * grid.h).fill(Infinity);
  const score = new Float64Array(grid.w * grid.h).fill(Infinity);
  const came = new Int32Array(grid.w * grid.h).fill(-1);
  const closed = new Uint8Array(grid.w * grid.h);
  cost[startIndex] = 0;
  score[startIndex] = octile(from.x, from.y, goal.x, goal.y);
  const open = new Heap(score);
  open.push(startIndex);
  while (open.size > 0) {
    const current = open.pop();
    if (current === goalIndex) break;
    if (closed[current]) continue;
    closed[current] = 1;
    const cx = current % w;
    const cy = (current - cx) / w;
    for (const [dx, dy, step] of STEPS) {
      const nx = cx + dx;
      const ny = cy + dy;
      if (!free(grid, nx, ny)) continue;
      if (dx !== 0 && dy !== 0 && (!free(grid, cx + dx, cy) || !free(grid, cx, cy + dy))) continue;
      const next = ny * w + nx;
      const tentative = cost[current]! + step;
      if (tentative >= cost[next]!) continue;
      cost[next] = tentative;
      came[next] = current;
      score[next] = tentative + octile(nx, ny, goal.x, goal.y);
      open.push(next);
    }
  }
  if (cost[goalIndex] === Infinity) return null;
  const path: Cell[] = [];
  for (let at = goalIndex; at !== -1; at = came[at]!) {
    path.push({ x: at % w, y: Math.floor(at / w) });
    if (at === startIndex) break;
  }
  return path.reverse();
}

export function pathLength(path: Cell[]): number {
  let total = 0;
  for (let i = 1; i < path.length; i++) {
    total += Math.hypot(path[i]!.x - path[i - 1]!.x, path[i]!.y - path[i - 1]!.y);
  }
  return total;
}
