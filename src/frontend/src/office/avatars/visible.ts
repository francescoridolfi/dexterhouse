// SPDX-License-Identifier: AGPL-3.0-or-later
// Which avatars are drawn: beyond 25 agents resting in the break room a counter replaces
// the extra avatars (office_layout.md, NFR-P3).
import type { AvatarModel } from "../state/model.ts";

export const MAX_AVATARS = 64;
export const BREAK_ROOM_LIMIT = 25;

/** Visible avatars this frame, in instance order (index → agent id). */
export function visibleAvatars(avatars: AvatarModel[]): AvatarModel[] {
  let resting = 0;
  return [...avatars]
    .sort((a, b) => a.id.localeCompare(b.id))
    .filter((a) => {
      if (a.room !== "break_room" || a.walking) return true;
      resting += 1;
      return resting <= BREAK_ROOM_LIMIT;
    })
    .slice(0, MAX_AVATARS);
}
