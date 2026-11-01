// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { tooSlow } from "../scene/perf.ts";
import { emptyOffice } from "../state/model.ts";
import { moveTo, newAvatar } from "../state/placement.ts";
import { WALK_SPEED, startMotion, stepMotion } from "./motion.ts";
import { visibleAvatars } from "./visible.ts";

function walker(hurry = false) {
  const office = emptyOffice();
  const idle = newAvatar(office, "a", "break_room", 0);
  return { ...moveTo(office, idle, "qa_lab"), hurry, origin: idle.cell };
}

function run(avatar: ReturnType<typeof walker>, teleport: boolean, maxS = 60) {
  const rt = startMotion(avatar);
  rt.opacity = 1;
  for (let t = 0; t < maxS; t += 0.05) {
    if (stepMotion(rt, avatar, 0.05, teleport)) return { rt, seconds: t + 0.05 };
  }
  return { rt, seconds: Infinity };
}

describe("stepMotion", () => {
  it("walks the A* path at 1.4 cells/s and arrives on the target cell", () => {
    const avatar = walker();
    const { rt, seconds } = run(avatar, false);
    expect(seconds).toBeLessThan(Infinity);
    expect(Math.floor(rt.x)).toBe(avatar.cell.x);
    expect(Math.floor(rt.z)).toBe(avatar.cell.y);
    const straight = Math.hypot(avatar.cell.x - avatar.origin.x, avatar.cell.y - avatar.origin.y);
    expect(seconds).toBeGreaterThanOrEqual(straight / WALK_SPEED - 0.1);
  });

  it("walks twice as fast in a hurry", () => {
    const slow = run(walker(false), false).seconds;
    const fast = run(walker(true), false).seconds;
    expect(fast).toBeLessThan(slow * 0.6);
  });

  it("teleports with a fade under reduced motion", () => {
    const avatar = walker();
    const { rt, seconds } = run(avatar, true);
    expect(seconds).toBeLessThan(1);
    expect(rt.x).toBe(avatar.cell.x + 0.5);
    expect(rt.opacity).toBeCloseTo(1);
  });
});

describe("performance rules", () => {
  it("falls back after 10 s under 20 fps, not before", () => {
    expect(tooSlow(Array<number>(9).fill(5))).toBe(false);
    expect(tooSlow([...Array<number>(9).fill(12), 25])).toBe(false);
    expect(tooSlow([60, ...Array<number>(10).fill(19)])).toBe(true);
  });

  it("shows at most 25 resting avatars in the break room", () => {
    const office = emptyOffice();
    const avatars = Array.from({ length: 30 }, (_, i) =>
      newAvatar(office, `a${i}`, "break_room", 0),
    );
    expect(visibleAvatars(avatars)).toHaveLength(25);
  });
});
