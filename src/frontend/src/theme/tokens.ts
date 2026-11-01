// SPDX-License-Identifier: AGPL-3.0-or-later
// Single source of the palette (ux/theme.md): CSS variables for the 2D, colours for the 3D.
import tokens from "./tokens.json";

export type ColorToken = keyof typeof tokens.color;
export type Scheme = "light" | "dark";

export const palette = tokens.color;
export const roomColors: Record<string, string> = tokens.room;
export const roleColors: Record<string, string> = tokens.role;
export const motion = tokens.motion;

/** Fallback categorical palette for agents whose package declares no colour. */
const CATEGORICAL = ["#7DB7E7", "#B48CE7", "#E7D77D", "#E79D7D", "#7DE7B8", "#7D9CE7", "#E77DA6"];

export function colorFor(scheme: Scheme, token: ColorToken): string {
  return palette[token][scheme];
}

/** Agent colour: package `office.color`, else the built-in role colour, else categorical. */
export function agentColor(role: string, avatarColor?: unknown): string {
  if (typeof avatarColor === "string" && /^#[0-9a-fA-F]{6}$/.test(avatarColor)) return avatarColor;
  const known = roleColors[role];
  if (known) return known;
  let hash = 0;
  for (const ch of role) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return CATEGORICAL[hash % CATEGORICAL.length] ?? "#9CA3AF";
}

export function roomColor(room: string): string {
  return roomColors[room] ?? "#C9C9C9";
}
