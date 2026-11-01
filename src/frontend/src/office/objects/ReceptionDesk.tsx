// SPDX-License-Identifier: AGPL-3.0-or-later
// Reception: the bell (open gates, click → shared GatePanel), the budget lamp (click → Costs)
// and the project folder (reception → archive when the project ends).
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { Group } from "three";

import { eur } from "../../utils/format.ts";
import { budgetLevel } from "../../store/selectors.ts";
import { useOffice, useProject, useRuntime } from "../scene/context.ts";
import type { ScenePalette } from "../utils/colors.ts";
import { GEOMETRY, glow, toon } from "../utils/materials.ts";
import { anchor, hoverHandlers } from "./anchors.ts";

const BELL = anchor("bell");
const LAMP = anchor("budget_lamp");
const ARCHIVE = anchor("documents", "archive");

export function ReceptionDesk({ palette }: { palette: ScenePalette }) {
  const { t } = useTranslation();
  const { runtime, actions, clock } = useOffice();
  const gates = useProject((s) => s.gates);
  const budget = useProject((s) => s.budget);
  const project = useProject((s) => s.project);
  const folder = useRuntime((s) => s.model.folder);
  const open = useMemo(
    () =>
      Object.values(gates)
        .filter((g) => g.status === "open")
        .sort((a, b) => a.openedAt.localeCompare(b.openedAt)),
    [gates],
  );
  const level = budgetLevel(budget.spent, budget.budget);
  const bell = useRef<Group>(null);
  const bellGlow = useMemo(() => glow(), []);
  const lampGlow = useMemo(() => glow(), []);
  const folderMat = useMemo(() => toon(palette.token("accent")), [palette]);

  useFrame(() => {
    const now = clock();
    const state = runtime.getState();
    const ringing = open.length > 0 && !state.fast;
    if (bell.current) {
      const shake = ringing && state.model.bellRingUntil > now ? Math.sin(now / 40) * 0.25 : 0;
      bell.current.rotation.z = shake;
    }
    const blink = ringing ? 0.55 + 0.45 * Math.abs(Math.sin(now / 300)) : 1;
    bellGlow.color
      .set(open.length ? palette.token("status-blocked") : palette.token("muted"))
      .multiplyScalar(blink);
    lampGlow.color.set(palette.token(`budget-${level}`));
  });

  const folderAt = folder === "archive" ? ARCHIVE : { x: BELL.x + 1.2, z: BELL.z };
  return (
    <group>
      <group
        ref={bell}
        position={[BELL.x, 1.1, BELL.z]}
        onClick={(event) => {
          event.stopPropagation();
          if (event.delta > 4) return; // a drag that pans the view
          const gate = open.find((g) => g.type === "escalation") ?? open[0];
          if (gate) actions.openGate(gate.id);
        }}
        {...hoverHandlers(runtime, () => t("office.hover.bell", { count: open.length }))}
      >
        <mesh
          geometry={GEOMETRY.ball}
          material={bellGlow}
          scale={[0.3, 0.26, 0.3]}
          position={[0, 0.1, 0]}
        />
      </group>
      <mesh
        geometry={GEOMETRY.ball}
        material={lampGlow}
        position={[LAMP.x, 1.55, LAMP.z]}
        scale={0.24}
        onClick={(event) => {
          event.stopPropagation();
          if (event.delta > 4) return; // a drag that pans the view
          actions.openCosts();
        }}
        {...hoverHandlers(runtime, () =>
          t("office.hover.budget", { spent: eur(budget.spent), budget: eur(budget.budget) }),
        )}
      />
      <mesh
        geometry={GEOMETRY.box}
        material={folderMat}
        position={[folderAt.x, folder === "archive" ? 0.8 : 1.1, folderAt.z]}
        scale={[0.35, 0.06, 0.26]}
        {...hoverHandlers(runtime, () =>
          project
            ? `${project.name} · ${t(`status.${project.status}`, { defaultValue: project.status })}`
            : null,
        )}
      />
    </group>
  );
}
