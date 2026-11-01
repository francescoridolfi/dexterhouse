// SPDX-License-Identifier: AGPL-3.0-or-later
// Every avatar in 5 instanced meshes (torso, head, legs, arms, halo): one shared update loop,
// at 30 Hz above 12 avatars (NFR-P3). Positions live in `motion`, never in React state.
import { type ThreeEvent, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  BoxGeometry,
  Color,
  Euler,
  type InstancedMesh,
  Matrix4,
  Quaternion,
  TorusGeometry,
  Vector3,
} from "three";

import { useOffice } from "../scene/context.ts";
import { avatarMode } from "../state/mode.ts";
import type { ScenePalette } from "../utils/colors.ts";
import { GEOMETRY, glow, toon } from "../utils/materials.ts";
import { stepMotion, startMotion } from "./motion.ts";
import { MAX_AVATARS, visibleAvatars } from "./visible.ts";
import { pose } from "./pose.ts";

const SKIN = new Color("#F1C27D");
const LIMB = new BoxGeometry(1, 1, 1).translate(0, -0.5, 0);
const HALO = new TorusGeometry(0.28, 0.04, 6, 16).rotateX(Math.PI / 2);

const m = new Matrix4();
const base = new Matrix4();
const euler = new Euler();
const local = new Matrix4();
const q = new Quaternion();
const up = new Vector3(0, 1, 0);
const v = new Vector3();
const s = new Vector3();
const color = new Color();

export function Avatars({
  palette,
  onSelect,
}: {
  palette: ScenePalette;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const { runtime, motion, clock, project, timeScale } = useOffice();
  const torso = useRef<InstancedMesh>(null);
  const head = useRef<InstancedMesh>(null);
  const legs = useRef<InstancedMesh>(null);
  const arms = useRef<InstancedMesh>(null);
  const halo = useRef<InstancedMesh>(null);
  const order = useRef<string[]>([]);
  const pending = useRef(0);
  const material = useMemo(() => toon(), []);
  const haloMaterial = useMemo(() => glow(palette.token("status-blocked")), [palette]);

  useFrame((_, delta) => {
    const mt = torso.current;
    const mh = head.current;
    const ml = legs.current;
    const ma = arms.current;
    const mo = halo.current;
    if (!mt || !mh || !ml || !ma || !mo) return;
    const state = runtime.getState();
    const all = Object.values(state.model.avatars);
    pending.current += delta;
    if (all.length > 12 && pending.current < 1 / 30) return;
    const dt = Math.min(pending.current, 0.1) * timeScale();
    pending.current = 0;
    const now = clock();
    const agents = project.getState().agents;
    const shown = visibleAvatars(all);
    order.current = shown.map((a) => a.id);
    const arrived: string[] = [];
    let halos = 0;
    shown.forEach((avatar, i) => {
      let rt = motion.get(avatar.id);
      if (!rt) motion.set(avatar.id, (rt = startMotion(avatar)));
      if (stepMotion(rt, avatar, dt, state.fast)) arrived.push(avatar.id);
      const mode = avatarMode(avatar, now);
      const seated = !!avatar.seat && !rt.moving && !avatar.walking;
      const p = pose(mode, rt.anim, rt.moving, seated);
      const scale = rt.opacity;
      base.compose(
        v.set(rt.x, p.lift, rt.z),
        q.setFromAxisAngle(up, rt.heading),
        s.set(scale, scale, scale),
      );
      const part = (
        mesh: InstancedMesh,
        index: number,
        x: number,
        y: number,
        z: number,
        sx: number,
        sy: number,
        sz: number,
        rx = 0,
        rz = 0,
      ) => {
        local.makeRotationFromEuler(euler.set(rx, 0, rz));
        local.setPosition(x, y, z);
        local.scale(s.set(sx, sy, sz));
        mesh.setMatrixAt(index, m.multiplyMatrices(base, local));
      };
      const agent = agents[avatar.id];
      const body = palette.agent(agent?.role ?? "agent", agent?.color);
      part(mt, i, 0, 0.7, 0, 0.42, 0.5, 0.26);
      mt.setColorAt(i, body);
      part(mh, i, 0, 1.11, 0, 0.32, 0.32, 0.32);
      mh.setColorAt(i, SKIN);
      const legColor = color.copy(body).multiplyScalar(0.55);
      part(ml, 2 * i, -0.1, 0.45, 0, 0.14, 0.45, 0.16, p.legL);
      part(ml, 2 * i + 1, 0.1, 0.45, 0, 0.14, 0.45, 0.16, p.legR);
      ml.setColorAt(2 * i, legColor);
      ml.setColorAt(2 * i + 1, legColor);
      part(ma, 2 * i, -0.27, 0.92, 0, 0.11, 0.42, 0.12, p.armL, -p.armOut);
      part(ma, 2 * i + 1, 0.27, 0.92, 0, 0.11, 0.42, 0.12, p.armR, p.armOut);
      ma.setColorAt(2 * i, body);
      ma.setColorAt(2 * i + 1, body);
      if (mode === "blocked") {
        mo.setMatrixAt(halos++, m.makeTranslation(rt.x, 1.45 + Math.sin(rt.anim * 3) * 0.03, rt.z));
      }
    });
    for (const mesh of [mt, mh, ml, ma, mo]) mesh.instanceMatrix.needsUpdate = true;
    for (const mesh of [mt, mh, ml, ma])
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mt.count = mh.count = shown.length;
    ml.count = ma.count = shown.length * 2;
    mo.count = halos;
    for (const id of arrived) state.arrive(id);
    for (const id of motion.keys()) if (!state.model.avatars[id]) motion.delete(id);
  });

  const target = (event: ThreeEvent<PointerEvent | MouseEvent>) => {
    const index = event.instanceId ?? -1;
    const mesh = event.object as InstancedMesh;
    const perAvatar = mesh === legs.current || mesh === arms.current ? 2 : 1;
    return order.current[Math.floor(index / perAvatar)];
  };
  const hover = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
    const id = target(event);
    const state = project.getState();
    const agent = id ? state.agents[id] : undefined;
    const avatar = id ? runtime.getState().model.avatars[id] : undefined;
    if (!agent || !avatar) return;
    const task = Object.values(state.tasks).find(
      (x) => x.assigned_agent === id && x.status === "in_progress",
    );
    const text = [
      `${agent.displayName} · ${t(`role.${agent.role}`, { defaultValue: agent.role })}`,
      t(`office.mode.${avatarMode(avatar, clock())}`),
      task ? `${task.external_id} ${task.title}` : agent.purpose,
    ]
      .filter(Boolean)
      .join("\n");
    runtime
      .getState()
      .setHover({ text, x: event.nativeEvent.clientX, y: event.nativeEvent.clientY });
  };
  const handlers = {
    onPointerMove: hover,
    onPointerOut: () => runtime.getState().setHover(null),
    onClick: (event: ThreeEvent<MouseEvent>) => {
      event.stopPropagation();
      if (event.delta > 4) return; // a drag that pans the view
      const id = target(event);
      if (id) onSelect(id);
    },
  };
  return (
    <group>
      <instancedMesh
        ref={torso}
        args={[GEOMETRY.box, material, MAX_AVATARS]}
        frustumCulled={false}
        {...handlers}
      />
      <instancedMesh
        ref={head}
        args={[GEOMETRY.box, material, MAX_AVATARS]}
        frustumCulled={false}
        {...handlers}
      />
      <instancedMesh
        ref={legs}
        args={[LIMB, material, MAX_AVATARS * 2]}
        frustumCulled={false}
        {...handlers}
      />
      <instancedMesh
        ref={arms}
        args={[LIMB, material, MAX_AVATARS * 2]}
        frustumCulled={false}
        {...handlers}
      />
      <instancedMesh ref={halo} args={[HALO, haloMaterial, MAX_AVATARS]} frustumCulled={false} />
    </group>
  );
}
