// SPDX-License-Identifier: AGPL-3.0-or-later
// Floors, walls, furniture and chairs: two instanced meshes (boxes, cylinders) for the plan.
import type { ThreeEvent } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import { Color, type InstancedMesh, Matrix4, Quaternion, Vector3 } from "three";

import { GEOMETRY, toon } from "../utils/materials.ts";
import type { ScenePalette } from "../utils/colors.ts";
import { type Instance, staticInstances } from "./staticInstances.ts";

function fill(mesh: InstancedMesh, items: Instance[], palette: ScenePalette) {
  const matrix = new Matrix4();
  const q = new Quaternion();
  const up = new Vector3(0, 1, 0);
  const color = new Color();
  items.forEach((item, i) => {
    q.setFromAxisAngle(up, item.rotY);
    matrix.compose(new Vector3(item.x, item.y, item.z), q, new Vector3(item.sx, item.sy, item.sz));
    mesh.setMatrixAt(i, matrix);
    if (item.color === "wall") color.copy(palette.wall);
    else if (item.color.startsWith("floor:")) color.copy(palette.floor(item.color.slice(6)));
    else color.set(item.color);
    mesh.setColorAt(i, color);
  });
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  mesh.computeBoundingSphere();
}

export function Furniture({
  palette,
  onFloorClick,
}: {
  palette: ScenePalette;
  onFloorClick: (event: ThreeEvent<MouseEvent>) => void;
}) {
  const items = useMemo(() => staticInstances(), []);
  const boxes = useMemo(() => items.filter((i) => i.shape === "box"), [items]);
  const cyls = useMemo(() => items.filter((i) => i.shape === "cyl"), [items]);
  const material = useMemo(() => toon(), []);
  const boxMesh = useRef<InstancedMesh>(null);
  const cylMesh = useRef<InstancedMesh>(null);
  useLayoutEffect(() => {
    if (boxMesh.current) fill(boxMesh.current, boxes, palette);
    if (cylMesh.current) fill(cylMesh.current, cyls, palette);
  }, [boxes, cyls, palette]);
  return (
    <group>
      <instancedMesh
        ref={boxMesh}
        args={[GEOMETRY.box, material, boxes.length]}
        onClick={onFloorClick}
        frustumCulled={false}
      />
      <instancedMesh ref={cylMesh} args={[GEOMETRY.cyl, material, cyls.length]} />
    </group>
  );
}
