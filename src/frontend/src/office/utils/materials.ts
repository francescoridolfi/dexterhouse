// SPDX-License-Identifier: AGPL-3.0-or-later
// Shared geometries and the 3-step toon material (ux/theme.md): created once per page.
import {
  BoxGeometry,
  CylinderGeometry,
  DataTexture,
  MeshBasicMaterial,
  MeshToonMaterial,
  NearestFilter,
  RedFormat,
  SphereGeometry,
} from "three";

let gradient: DataTexture | null = null;

export function toonGradient(): DataTexture {
  if (!gradient) {
    gradient = new DataTexture(new Uint8Array([90, 170, 255]), 3, 1, RedFormat);
    gradient.minFilter = NearestFilter;
    gradient.magFilter = NearestFilter;
    gradient.needsUpdate = true;
  }
  return gradient;
}

export function toon(color = "#ffffff"): MeshToonMaterial {
  return new MeshToonMaterial({ color, gradientMap: toonGradient() });
}

/** Unlit material: screens, lamps, room lights (emissive look without real lights). */
export function glow(color = "#ffffff", opacity = 1): MeshBasicMaterial {
  return new MeshBasicMaterial({ color, transparent: opacity < 1, opacity, toneMapped: false });
}

export const GEOMETRY = {
  box: new BoxGeometry(1, 1, 1),
  cyl: new CylinderGeometry(0.5, 0.5, 1, 10),
  ball: new SphereGeometry(0.5, 8, 6),
};
