// SPDX-License-Identifier: AGPL-3.0-or-later
// Documents on the producing room's table, then in the archive: at most 5 sheets per table,
// then a pile (one instanced mesh for all). Click → artifact panel.
import { useLayoutEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Color, type InstancedMesh, Matrix4 } from "three";

import { useOffice, useRuntime } from "../scene/context.ts";
import type { DocumentModel } from "../state/model.ts";
import { GEOMETRY, toon } from "../utils/materials.ts";
import { anchors, hoverHandlers } from "./anchors.ts";

const TABLES = anchors("documents");
const PER_TABLE = 5;
const MAX = TABLES.length * (PER_TABLE + 1);

interface Sheet {
  doc: DocumentModel;
  count: number;
}

function sheets(documents: Record<string, DocumentModel>): { at: Matrix4; sheet: Sheet }[] {
  const out: { at: Matrix4; sheet: Sheet }[] = [];
  for (const table of TABLES) {
    const here = Object.values(documents).filter((d) => d.room === table.room);
    const visible = here.slice(-PER_TABLE);
    visible.forEach((doc, i) => {
      const pile = here.length > PER_TABLE && i === 0;
      const height = pile ? 0.04 * Math.min(here.length - PER_TABLE + 1, 8) : 0.02;
      out.push({
        at: new Matrix4()
          .makeScale(0.28, height, 0.36)
          .setPosition(
            table.x - 0.3 + (i % 3) * 0.3,
            0.8 + height / 2,
            table.z - 0.15 + Math.floor(i / 3) * 0.32,
          ),
        sheet: { doc, count: pile ? here.length - PER_TABLE + 1 : 1 },
      });
    });
  }
  return out.slice(0, MAX);
}

export function Documents() {
  const { t } = useTranslation();
  const { runtime, actions } = useOffice();
  const documents = useRuntime((s) => s.model.documents);
  const items = useMemo(() => sheets(documents), [documents]);
  const mesh = useRef<InstancedMesh>(null);
  const material = useMemo(() => toon(), []);

  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    const paper = new Color("#FAFAF7");
    const pile = new Color("#E7D9B5");
    items.forEach((item, i) => {
      m.setMatrixAt(i, item.at);
      m.setColorAt(i, item.sheet.count > 1 ? pile : paper);
    });
    m.count = items.length;
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    m.computeBoundingSphere();
  }, [items]);

  return (
    <instancedMesh
      ref={mesh}
      args={[GEOMETRY.box, material, MAX]}
      frustumCulled={false}
      onClick={(event) => {
        event.stopPropagation();
        if (event.delta > 4) return; // a drag that pans the view
        const item = items[event.instanceId ?? -1];
        if (item) actions.openArtifact(item.sheet.doc.id);
      }}
      {...hoverHandlers(runtime, (id) => {
        const item = items[id ?? -1];
        if (!item) return null;
        const { doc, count } = item.sheet;
        const label = t("office.hover.document", {
          kind: t(`kind.${doc.kind}`, { defaultValue: doc.kind }),
          version: doc.version,
        });
        return count > 1 ? `${label}\n${t("office.hover.pile", { count })}` : label;
      })}
    />
  );
}
