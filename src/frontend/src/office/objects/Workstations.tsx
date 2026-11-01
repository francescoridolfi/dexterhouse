// SPDX-License-Identifier: AGPL-3.0-or-later
// Open-space PCs (`workspace.*`: on, standby, off) and the HR package box (`package.*`).
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Color, type InstancedMesh, Matrix4 } from "three";

import { useOffice, useRuntime } from "../scene/context.ts";
import { avatarMode } from "../state/mode.ts";
import type { ScenePalette } from "../utils/colors.ts";
import { GEOMETRY, glow, toon } from "../utils/materials.ts";
import { anchor, anchors, hoverHandlers } from "./anchors.ts";

const PCS = anchors("workspace_pc");
const BOX = anchor("package_box");

export function Workstations({ palette }: { palette: ScenePalette }) {
  const { t } = useTranslation();
  const { runtime, clock, actions } = useOffice();
  const pcs = useRuntime((s) => s.model.pcs);
  const box = useRuntime((s) => s.model.packageBox);
  const screens = useRef<InstancedMesh>(null);
  const screenMat = useMemo(() => glow(), []);
  const matrix = useMemo(() => new Matrix4(), []);
  const boxMat = useMemo(() => toon("#C8A27A"), []);
  const tapeMat = useMemo(() => glow(), []);
  const colors = useMemo(
    () => ({
      on: new Color(palette.token("status-working")),
      standby: new Color(palette.token("muted")).multiplyScalar(0.6),
      off: new Color("#111827"),
    }),
    [palette],
  );

  useFrame(() => {
    const m = screens.current;
    if (!m) return;
    const now = clock();
    const avatars = Object.values(runtime.getState().model.avatars);
    PCS.forEach((pc, i) => {
      // Desks come in pairs of rows: the seat is north of the first row, south of the second.
      const seatDy = pc.prop.y % 2 === 0 ? -1 : 1;
      const user = avatars.find(
        (a) => a.seat && a.seat.x === pc.prop.x && a.seat.y === pc.prop.y + seatDy,
      );
      const busy = user && !user.walking && avatarMode(user, now) === "working";
      m.setMatrixAt(
        i,
        matrix.makeScale(0.46, 0.3, 0.03).setPosition(pc.x, 0.99, pc.z - seatDy * 0.25),
      );
      m.setColorAt(
        i,
        busy || pcs === "on" ? colors.on : pcs === "standby" ? colors.standby : colors.off,
      );
    });
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    if (box) {
      tapeMat.color.set(
        palette.token(
          box.state === "installed"
            ? "status-done"
            : box.state === "rejected"
              ? "status-failed"
              : "status-blocked",
        ),
      );
    }
  });

  return (
    <group>
      <instancedMesh
        ref={screens}
        args={[GEOMETRY.box, screenMat, PCS.length]}
        frustumCulled={false}
        {...hoverHandlers(runtime, () => t(`office.hover.pcs.${pcs}`))}
      />
      {box ? (
        <group
          position={[BOX.x, 0, BOX.z]}
          onClick={(event) => {
            event.stopPropagation();
            if (event.delta > 4) return; // a drag that pans the view
            actions.openPackages();
          }}
          {...hoverHandlers(runtime, () =>
            t(`office.hover.package.${box.state}`, { name: box.name }),
          )}
        >
          <mesh geometry={GEOMETRY.box} material={boxMat} position={[0, 0.42, 0]} scale={0.6} />
          <mesh
            geometry={GEOMETRY.box}
            material={tapeMat}
            position={[0, 0.73, 0]}
            scale={[0.62, 0.03, 0.14]}
          />
        </group>
      ) : null}
    </group>
  );
}
