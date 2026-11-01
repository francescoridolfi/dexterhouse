// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { type FloorGrid, GRID } from "../rooms/grid.ts";
import { findPath, nearestFree, pathLength } from "./pathfinding.ts";

/** `#` blocked, `.` free. */
function grid(rows: string[]): FloorGrid {
  const h = rows.length;
  const w = rows[0]!.length;
  const blocked = new Uint8Array(w * h);
  rows.forEach((row, y) => [...row].forEach((c, x) => (blocked[y * w + x] = c === "#" ? 1 : 0)));
  return { w, h, walls: blocked, blocked };
}

describe("findPath", () => {
  it("walks straight and diagonally on open floor", () => {
    const open = grid(["....", "....", "...."]);
    expect(findPath(open, { x: 0, y: 0 }, { x: 3, y: 0 })).toHaveLength(4);
    const diagonal = findPath(open, { x: 0, y: 0 }, { x: 2, y: 2 })!;
    expect(diagonal).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 1 },
      { x: 2, y: 2 },
    ]);
    expect(pathLength(diagonal)).toBeCloseTo(2 * Math.SQRT2);
  });

  it("goes around walls without cutting corners", () => {
    const wall = grid([".#.", ".#.", "..."]);
    const path = findPath(wall, { x: 0, y: 0 }, { x: 2, y: 0 })!;
    expect(path[0]).toEqual({ x: 0, y: 0 });
    expect(path.at(-1)).toEqual({ x: 2, y: 0 });
    expect(path.some((c) => c.y === 2)).toBe(true);
    for (let i = 1; i < path.length; i++) {
      const a = path[i - 1]!;
      const b = path[i]!;
      if (a.x !== b.x && a.y !== b.y) {
        expect(wall.blocked[a.y * 3 + b.x]).toBe(0);
        expect(wall.blocked[b.y * 3 + a.x]).toBe(0);
      }
    }
  });

  it("returns null for blocked or unreachable goals", () => {
    const closed = grid([".#.", "##.", "..."]);
    expect(findPath(closed, { x: 0, y: 0 }, { x: 2, y: 2 })).toBeNull();
    expect(findPath(closed, { x: 2, y: 2 }, { x: 1, y: 1 })).toBeNull();
  });

  it("starts from the nearest free cell when the start is blocked", () => {
    const g = grid(["...", ".#.", "..."]);
    expect(nearestFree(g, { x: 1, y: 1 })).not.toEqual({ x: 1, y: 1 });
    expect(findPath(g, { x: 1, y: 1 }, { x: 2, y: 2 })).not.toBeNull();
  });

  it("crosses the office from the reception to the release dock through doors", () => {
    const path = findPath(GRID, { x: 12, y: 10 }, { x: 30, y: 26 })!;
    expect(path).not.toBeNull();
    for (const cell of path) expect(GRID.blocked[cell.y * GRID.w + cell.x]).toBe(0);
    expect(pathLength(path)).toBeGreaterThan(20);
  });
});
