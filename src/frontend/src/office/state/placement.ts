// SPDX-License-Identifier: AGPL-3.0-or-later
// Seat bookkeeping for the office reducer: moving an avatar frees its seat and takes another.
import { key, place } from "../rooms/occupancy.ts";
import { PLAN, type RoomDef, roomById } from "../rooms/plan.ts";
import { resolveRoom } from "../rooms/roomFor.ts";
import type { AvatarModel, OfficeModel } from "./model.ts";

export const IDLE = "break_room";

function taken(model: OfficeModel, room: string, except: string): Set<string> {
  const cells = new Set<string>();
  for (const avatar of Object.values(model.avatars)) {
    if (avatar.id !== except && avatar.room === room && !avatar.leaving)
      cells.add(key(avatar.cell));
  }
  return cells;
}

export function newAvatar(
  model: OfficeModel,
  id: string,
  roomId: string,
  now: number,
): AvatarModel {
  const room = resolveRoom(roomId);
  const spot = place(room, taken(model, room.id, id));
  return {
    id,
    room: room.id,
    cell: spot.cell,
    seat: spot.seat,
    origin: spot.cell,
    errand: null,
    walking: false,
    hurry: false,
    working: false,
    turnId: null,
    purpose: null,
    blockedBy: null,
    leaving: false,
    tool: null,
    toolUntil: 0,
    failedUntil: 0,
    alarmUntil: 0,
    celebrateUntil: 0,
    summary: null,
    summaryUntil: 0,
    bornAt: now,
  };
}

/** The avatar's truth becomes `roomId`: book a seat there and walk unless already seated. */
export function moveTo(model: OfficeModel, avatar: AvatarModel, roomId: string): AvatarModel {
  const room: RoomDef = resolveRoom(roomId);
  if (room.id === avatar.room && !avatar.errand) return avatar;
  const spot = place(room, taken(model, room.id, avatar.id));
  return {
    ...avatar,
    room: room.id,
    cell: spot.cell,
    seat: spot.seat,
    errand: null,
    walking: true,
  };
}

/** A free cell just inside the room, for hand-off errands (the agent does not sit). */
export function errandTo(model: OfficeModel, avatar: AvatarModel, roomId: string): AvatarModel {
  const room = roomById(roomId);
  if (!room || room.id === avatar.room) return avatar;
  const spot = place({ ...room, seats: [] }, taken(model, room.id, avatar.id));
  return { ...avatar, errand: { room: room.id, cell: spot.cell }, walking: true };
}

export function leave(avatar: AvatarModel): AvatarModel {
  return {
    ...avatar,
    leaving: true,
    walking: true,
    errand: null,
    working: false,
    room: "reception",
    cell: PLAN.exit,
    seat: null,
  };
}

export function put(model: OfficeModel, avatar: AvatarModel): OfficeModel {
  return { ...model, avatars: { ...model.avatars, [avatar.id]: avatar } };
}
