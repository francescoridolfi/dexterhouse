// SPDX-License-Identifier: AGPL-3.0-or-later
// Occupancy rules (office_layout.md): first free seat, else stand on a free cell of the room.
import { type FloorGrid, GRID, isFree } from "./grid.ts";
import { type Cell, type RoomDef, type Seat, interior, roomCenter } from "./plan.ts";

export interface Placement {
  cell: Cell;
  seat: Seat | null;
  standing: boolean;
}

export const key = (cell: Cell) => `${cell.x},${cell.y}`;

/** Where an agent goes in `room`, given the cells other agents already hold. */
export function place(room: RoomDef, taken: Set<string>, grid: FloorGrid = GRID): Placement {
  const seat = room.seats.find((s) => !taken.has(key(s)));
  if (seat) return { cell: { x: seat.x, y: seat.y }, seat, standing: false };
  const inner = interior(room.rect);
  const center = roomCenter(room);
  const doors = new Set(room.doors.map(key));
  const seats = new Set(room.seats.map(key));
  const cells: Cell[] = [];
  for (let y = inner.y; y < inner.y + inner.h; y++)
    for (let x = inner.x; x < inner.x + inner.w; x++) {
      const cell = { x, y };
      if (!isFree(grid, cell) || taken.has(key(cell)) || seats.has(key(cell))) continue;
      // Keep the cell in front of each door clear.
      const nearDoor = [...doors].some((d) => {
        const [dx = 0, dy = 0] = d.split(",").map(Number);
        return Math.abs(dx - x) + Math.abs(dy - y) <= 1;
      });
      if (!nearDoor) cells.push(cell);
    }
  cells.sort(
    (a, b) =>
      Math.hypot(a.x - center.x, a.y - center.y) - Math.hypot(b.x - center.x, b.y - center.y) ||
      a.y - b.y ||
      a.x - b.x,
  );
  const cell = cells[0] ?? room.doors[0] ?? { x: inner.x, y: inner.y };
  return { cell, seat: null, standing: true };
}
