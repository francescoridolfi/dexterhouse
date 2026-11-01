// SPDX-License-Identifier: AGPL-3.0-or-later
// 3D colours from theme/tokens.json (ux/theme.md): floors mix `surface` with the room colour
// at 15 %, room colours lose 30 % saturation in dark mode.
import { Color } from "three";

import {
  type ColorToken,
  type Scheme,
  agentColor,
  colorFor,
  roomColor,
} from "../../theme/tokens.ts";

export interface ScenePalette {
  scheme: Scheme;
  token: (token: ColorToken) => string;
  room: (roomId: string) => Color;
  floor: (roomId: string) => Color;
  wall: Color;
  agent: (role: string, color?: string) => Color;
}

function desaturate(hex: string, amount: number): Color {
  const color = new Color(hex);
  const hsl = { h: 0, s: 0, l: 0 };
  color.getHSL(hsl);
  return color.setHSL(hsl.h, hsl.s * (1 - amount), hsl.l);
}

export function scenePalette(dark: boolean): ScenePalette {
  const scheme: Scheme = dark ? "dark" : "light";
  const room = (id: string) => desaturate(roomColor(id), dark ? 0.3 : 0);
  const surface = new Color(colorFor(scheme, "surface"));
  return {
    scheme,
    token: (token) => colorFor(scheme, token),
    room,
    floor: (id) => surface.clone().lerp(room(id), 0.15),
    wall: dark ? surface.clone().offsetHSL(0, 0, 0.08) : new Color("#E8E4DA"),
    agent: (role, color) => new Color(agentColor(role, color)),
  };
}
