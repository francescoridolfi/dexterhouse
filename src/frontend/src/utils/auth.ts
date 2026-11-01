// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Role, User } from "../api/types.ts";

const RANK: Record<Role, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };

/** Role in the current organization (the first membership until the org switch exists). */
export function roleOf(user: User | undefined): Role {
  return user?.organizations[0]?.role ?? "viewer";
}

export function can(user: User | undefined, role: Role): boolean {
  return RANK[roleOf(user)] >= RANK[role];
}
