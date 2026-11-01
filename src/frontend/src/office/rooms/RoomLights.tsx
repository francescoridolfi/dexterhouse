// SPDX-License-Identifier: AGPL-3.0-or-later
// Room light = phase (emissive rug, not a real light): intensity 0.2 → 1 in 400 ms.
import { type ThreeEvent, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Color, type InstancedMesh, Matrix4 } from "three";

import { duration } from "../../utils/format.ts";
import { useOffice, useProject } from "../scene/context.ts";
import { GEOMETRY, glow } from "../utils/materials.ts";
import type { ScenePalette } from "../utils/colors.ts";
import { PLAN, interior } from "./plan.ts";
import { litRooms } from "./roomFor.ts";

const OFF = 0.2;

export function RoomLights({
  palette,
  onRoomClick,
}: {
  palette: ScenePalette;
  onRoomClick: (roomId: string) => void;
}) {
  const { t } = useTranslation();
  const { runtime, wallTime } = useOffice();
  const phases = useProject((s) => s.phases);
  const order = useProject((s) => s.phaseOrder);
  const lit = useMemo(() => litRooms({ phases, phaseOrder: order }), [phases, order]);
  const mesh = useRef<InstancedMesh>(null);
  const lamps = useRef<InstancedMesh>(null);
  const level = useRef(PLAN.rooms.map(() => OFF));
  const material = useMemo(() => glow("#ffffff", 0.55), []);
  const lampMaterial = useMemo(() => glow(), []);
  const matrices = useMemo(
    () =>
      PLAN.rooms.map((room) => {
        const inner = interior(room.rect);
        return new Matrix4()
          .makeScale(inner.w - 1, 0.02, inner.h - 1)
          .setPosition(inner.x + inner.w / 2, 0.01, inner.y + inner.h / 2);
      }),
    [],
  );
  // A lamp in the back corner of each room carries the hover and the click; the glowing
  // floor itself lets clicks through (the floor deselects).
  const lampAt = useMemo(
    () =>
      PLAN.rooms.map((room) => {
        const inner = interior(room.rect);
        return new Matrix4()
          .makeScale(0.45, 0.12, 0.45)
          .setPosition(inner.x + 0.5, 1.5, inner.y + 0.5);
      }),
    [],
  );
  const color = useMemo(() => new Color(), []);
  const dim = useMemo(() => new Color("#9CA3AF"), []);

  useFrame((_, dt) => {
    const m = mesh.current;
    const l = lamps.current;
    if (!m || !l) return;
    const fast = runtime.getState().fast;
    PLAN.rooms.forEach((room, i) => {
      const goal = lit.has(room.id) ? 1 : OFF;
      const now = level.current[i]!;
      const next = fast
        ? goal
        : now + Math.sign(goal - now) * Math.min(Math.abs(goal - now), dt / 0.4);
      level.current[i] = next;
      m.setMatrixAt(i, matrices[i]!);
      m.setColorAt(i, color.copy(palette.floor(room.id)).lerp(palette.room(room.id), next));
      l.setMatrixAt(i, lampAt[i]!);
      l.setColorAt(i, color.copy(dim).lerp(palette.room(room.id), next));
    });
    for (const x of [m, l]) {
      x.instanceMatrix.needsUpdate = true;
      if (x.instanceColor) x.instanceColor.needsUpdate = true;
    }
  });

  const hover = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
    const room = PLAN.rooms[event.instanceId ?? -1];
    if (!room) return;
    const phaseId = lit.get(room.id);
    const phase = phaseId ? phases[phaseId] : undefined;
    const since = phase?.startedAt ? (wallTime() - Date.parse(phase.startedAt)) / 1000 : null;
    const name = t(`room.${room.id}`, { defaultValue: room.id });
    const text = phase
      ? t("office.hover.roomPhase", {
          room: name,
          phase: t(`phase.${phase.phaseId}`, { defaultValue: phase.phaseId }),
          duration: since !== null && since > 0 ? duration(since) : "—",
        })
      : name;
    runtime
      .getState()
      .setHover({ text, x: event.nativeEvent.clientX, y: event.nativeEvent.clientY });
  };

  return (
    <group>
      <instancedMesh
        ref={mesh}
        args={[GEOMETRY.box, material, PLAN.rooms.length]}
        raycast={() => null}
      />
      <instancedMesh
        ref={lamps}
        args={[GEOMETRY.box, lampMaterial, PLAN.rooms.length]}
        frustumCulled={false}
        onPointerMove={hover}
        onPointerOut={() => runtime.getState().setHover(null)}
        onClick={(event) => {
          event.stopPropagation();
          if (event.delta > 4) return; // a drag that pans the view
          const room = PLAN.rooms[event.instanceId ?? -1];
          if (room) onRoomClick(room.id);
        }}
      />
    </group>
  );
}
