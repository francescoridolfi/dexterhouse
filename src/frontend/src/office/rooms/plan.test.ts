// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it, vi } from "vitest";

import { findPath } from "../utils/pathfinding.ts";
import { GRID, decodeWalls, isFree, roomAt } from "./grid.ts";
import { key, place } from "./occupancy.ts";
import { MANIFEST, PLAN, ROOM_IDS, roomById } from "./plan.ts";
import { resolveRoom } from "./roomFor.ts";
import { staticInstances } from "./staticInstances.ts";
import { planErrors } from "./validate.ts";

describe("office.json", () => {
  it("is a valid schema 1 plan with the 11 rooms", () => {
    expect(planErrors(PLAN, MANIFEST)).toEqual([]);
    expect(PLAN.rooms.map((r) => r.id).sort()).toEqual([...ROOM_IDS].sort());
    expect(PLAN.grid).toEqual({ w: 40, h: 30, cell_m: 1 });
  });

  it("reports what is wrong", () => {
    const broken = structuredClone(PLAN) as unknown as Record<string, unknown>;
    const rooms = broken.rooms as Record<string, unknown>[];
    rooms[0]!.id = "spa";
    (rooms[1]!.props as Record<string, unknown>[]).push({ model: "kenney/none", x: 1, y: 1 });
    rooms[2]!.capacity = 99;
    broken.walls = "rle:1,2";
    const errors = planErrors(broken, MANIFEST);
    expect(errors).toEqual(
      expect.arrayContaining([
        "missing room archive",
        "rooms.spa: unknown room id",
        expect.stringContaining("kenney/none not in the asset manifest"),
        "rooms.meeting_room: capacity must be ≤ seats.length",
        expect.stringContaining("walls:"),
      ]),
    );
  });

  it("decodes the RLE walls and keeps doors open", () => {
    const walls = decodeWalls(PLAN.walls, 40, 30);
    expect(walls[0]).toBe(1);
    for (const room of PLAN.rooms)
      for (const door of room.doors) expect(walls[door.y * 40 + door.x]).toBe(0);
    expect(() => decodeWalls("rle:5", 40, 30)).toThrow(/cover 5 cells/);
  });

  it("reaches every seat and door from the spawn point", () => {
    for (const room of PLAN.rooms) {
      for (const target of [...room.seats, ...room.doors]) {
        expect(isFree(GRID, target), `${room.id} ${key(target)}`).toBe(true);
        expect(findPath(GRID, PLAN.spawn, target), `${room.id} ${key(target)}`).not.toBeNull();
      }
    }
  });

  it("maps cells to rooms", () => {
    expect(roomAt(PLAN.spawn)).toBe("reception");
    expect(roomAt({ x: 3, y: 26 })).toBe("qa_lab");
    expect(roomAt({ x: 14, y: 26 })).toBeNull();
  });
});

describe("occupancy", () => {
  it("fills seats first, then stands on free cells", () => {
    const room = roomById("hr_office")!;
    const taken = new Set<string>();
    const first = place(room, taken);
    taken.add(key(first.cell));
    const second = place(room, taken);
    taken.add(key(second.cell));
    const third = place(room, taken);
    expect([first.standing, second.standing, third.standing]).toEqual([false, false, true]);
    expect(isFree(GRID, third.cell)).toBe(true);
    expect(roomAt(third.cell)).toBe("hr_office");
  });
});

describe("resolveRoom", () => {
  it("falls back to the open space with one warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expect(resolveRoom("qa_lab").id).toBe("qa_lab");
    expect(resolveRoom("rooftop").id).toBe("open_space");
    expect(resolveRoom("rooftop").id).toBe("open_space");
    expect(resolveRoom(null).id).toBe("open_space");
    expect(warn).toHaveBeenCalledTimes(1);
  });
});

describe("static geometry", () => {
  it("builds floors, walls, furniture and chairs within the budget", () => {
    const items = staticInstances();
    const walls = items.filter((i) => i.color === "wall");
    expect(items.filter((i) => i.color.startsWith("floor:"))).toHaveLength(11);
    expect(walls.length).toBeGreaterThan(20);
    expect(walls.length).toBeLessThan(200);
    const seats = PLAN.rooms.reduce((n, r) => n + r.seats.length, 0);
    expect(items.length).toBeGreaterThan(seats * 2);
    for (const item of items) expect(Number.isFinite(item.x + item.y + item.z)).toBe(true);
  });
});
