// SPDX-License-Identifier: AGPL-3.0-or-later
// QA traffic light (`test.run.*`, click → test report) and the release dock light, box and
// confetti (`release.*`). Confetti only without reduced motion.
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { BufferAttribute, BufferGeometry, type Points, PointsMaterial } from "three";

import type { ColorToken } from "../../theme/tokens.ts";
import { useOffice, useRuntime } from "../scene/context.ts";
import type { ScenePalette } from "../utils/colors.ts";
import { GEOMETRY, glow, toon } from "../utils/materials.ts";
import { anchor, hoverHandlers } from "./anchors.ts";

const LIGHT = anchor("test_light");
const DOCK = anchor("dock_light");
const CONFETTI = 160;
const LAMPS: { state: string; token: ColorToken; y: number }[] = [
  { state: "fail", token: "status-failed", y: 1.92 },
  { state: "running", token: "status-blocked", y: 1.6 },
  { state: "pass", token: "status-done", y: 1.28 },
];

export function Signals({ palette }: { palette: ScenePalette }) {
  const { t } = useTranslation();
  const { runtime, clock, actions } = useOffice();
  const test = useRuntime((s) => s.model.testLight);
  const dock = useRuntime((s) => s.model.dock);
  const lamps = useMemo(() => LAMPS.map(() => glow()), []);
  const dockMat = useMemo(() => glow(), []);
  const crateMat = useMemo(() => toon("#C8A27A"), []);
  const confetti = useRef<Points>(null);
  const confettiGeo = useMemo(() => {
    const geometry = new BufferGeometry();
    const positions = new Float32Array(CONFETTI * 3);
    const colors = new Float32Array(CONFETTI * 3);
    for (let i = 0; i < CONFETTI; i++) {
      colors.set([((i * 53) % 97) / 97, 0.5 + ((i * 29) % 13) / 26, ((i * 71) % 89) / 89], i * 3);
    }
    geometry.setAttribute("position", new BufferAttribute(positions, 3));
    geometry.setAttribute("color", new BufferAttribute(colors, 3));
    return geometry;
  }, []);
  const confettiMat = useMemo(() => new PointsMaterial({ size: 0.12, vertexColors: true }), []);

  useFrame(() => {
    const now = clock();
    const { fast, model } = runtime.getState();
    LAMPS.forEach((lamp, i) => {
      const on = test.state === lamp.state;
      const blink =
        on && lamp.state === "running" && !fast ? 0.5 + 0.5 * Math.abs(Math.sin(now / 250)) : 1;
      lamps[i]!.color.set(palette.token(lamp.token)).multiplyScalar(on ? blink : 0.18);
    });
    const tone: ColorToken =
      dock.state === "failed"
        ? "status-failed"
        : dock.state === "delivered"
          ? "status-done"
          : "accent";
    dockMat.color.set(palette.token(tone)).multiplyScalar(dock.state === "off" ? 0.2 : 1);
    const points = confetti.current;
    if (!points) return;
    const left = model.confettiUntil - now;
    points.visible = left > 0 && !fast;
    if (!points.visible) return;
    const position = confettiGeo.getAttribute("position") as BufferAttribute;
    const elapsed = 4 - left / 1000;
    for (let i = 0; i < CONFETTI; i++) {
      const angle = i * 2.399;
      const radius = 0.3 + ((i * 37) % 100) / 30;
      position.setXYZ(
        i,
        DOCK.x - 4 + Math.cos(angle + elapsed) * radius,
        Math.max(0, 3.5 - elapsed * (0.8 + (i % 7) / 10)),
        DOCK.z + 1 + Math.sin(angle + elapsed) * radius,
      );
    }
    position.needsUpdate = true;
  });

  return (
    <group>
      <group
        position={[LIGHT.x, 0, LIGHT.z]}
        onClick={(event) => {
          event.stopPropagation();
          if (event.delta > 4) return; // a drag that pans the view
          if (test.reportId) actions.openArtifact(test.reportId);
        }}
        {...hoverHandlers(runtime, () =>
          t(`office.hover.tests.${test.state}`, { detail: test.detail ?? "" }),
        )}
      >
        {LAMPS.map((lamp, i) => (
          <mesh
            key={lamp.state}
            geometry={GEOMETRY.ball}
            material={lamps[i]}
            position={[0, lamp.y, 0.14]}
            scale={0.2}
          />
        ))}
      </group>
      <group
        position={[DOCK.x, 0, DOCK.z]}
        {...hoverHandlers(runtime, () =>
          t(`office.hover.release.${dock.state}`, { detail: dock.detail ?? "" }),
        )}
      >
        <mesh geometry={GEOMETRY.ball} material={dockMat} position={[0, 1.95, 0]} scale={0.32} />
      </group>
      {dock.state === "prepared" || dock.state === "delivered" ? (
        <mesh
          geometry={GEOMETRY.box}
          material={crateMat}
          position={[DOCK.x - 3, 0.9, DOCK.z + 2]}
          scale={0.55}
        />
      ) : null}
      <points
        ref={confetti}
        geometry={confettiGeo}
        material={confettiMat}
        visible={false}
        frustumCulled={false}
      />
    </group>
  );
}
