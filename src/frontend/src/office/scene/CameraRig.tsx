// SPDX-License-Identifier: AGPL-3.0-or-later
// Drives the orthographic camera from the runtime: smooth rotation and zoom, follow-agent.
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { OrthographicCamera } from "three";

import { ZOOM_FACTORS, azimuth, cameraOffset, fitZoom } from "./camera.ts";
import { useOffice } from "./context.ts";

export function CameraRig() {
  const { runtime, motion } = useOffice();
  const current = useRef<{ az: number; zoom: number; x: number; z: number } | null>(null);

  useFrame((three, dt) => {
    const camera = three.camera as OrthographicCamera;
    const size = three.size;
    const { camera: wanted, fast } = runtime.getState();
    const followed = wanted.follow ? motion.get(wanted.follow) : undefined;
    const goal = {
      az: azimuth(wanted.orientation),
      zoom: fitZoom(size.width, size.height) * (ZOOM_FACTORS[wanted.zoom] ?? 1),
      x: followed?.x ?? wanted.target.x,
      z: followed?.z ?? wanted.target.z,
    };
    const now = (current.current ??= { ...goal });
    const k = fast ? 1 : 1 - Math.exp(-dt * 8);
    now.az += (goal.az - now.az) * k;
    now.zoom += (goal.zoom - now.zoom) * k;
    now.x += (goal.x - now.x) * k;
    now.z += (goal.z - now.z) * k;
    const [ox, oy, oz] = cameraOffset(now.az);
    camera.position.set(now.x + ox, oy, now.z + oz);
    camera.lookAt(now.x, 0, now.z);
    if (Math.abs(camera.zoom - now.zoom) > 1e-3) {
      camera.zoom = now.zoom;
      camera.updateProjectionMatrix();
    }
  });
  return null;
}
