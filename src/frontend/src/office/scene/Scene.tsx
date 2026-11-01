// SPDX-License-Identifier: AGPL-3.0-or-later
// Everything inside the R3F canvas: one directional + ambient light, plan, objects, avatars.
import { useMemo } from "react";

import { useDarkMode } from "../../utils/theme.ts";
import { Avatars } from "../avatars/Avatars.tsx";
import { Documents } from "../objects/Documents.tsx";
import { Kanban } from "../objects/Kanban.tsx";
import { ReceptionDesk } from "../objects/ReceptionDesk.tsx";
import { Signals } from "../objects/Signals.tsx";
import { Workstations } from "../objects/Workstations.tsx";
import { OverlaySync } from "../overlay/OverlaySync.tsx";
import { Furniture } from "../rooms/Furniture.tsx";
import { PLAN } from "../rooms/plan.ts";
import { RoomLights } from "../rooms/RoomLights.tsx";
import { scenePalette } from "../utils/colors.ts";
import { CameraRig } from "./CameraRig.tsx";
import { useOffice } from "./context.ts";
import { PerfMonitor } from "./PerfMonitor.tsx";

export function Scene({ active, onSlow }: { active: boolean; onSlow: () => void }) {
  const dark = useDarkMode();
  const palette = useMemo(() => scenePalette(dark), [dark]);
  const { runtime, actions } = useOffice();
  const bg = palette.token("bg");
  return (
    <>
      <color attach="background" args={[bg]} />
      <fog attach="fog" args={[bg, 90, 140]} />
      <ambientLight intensity={dark ? 1.1 : 1.4} />
      <directionalLight
        position={[PLAN.grid.w, 40, PLAN.grid.h + 20]}
        intensity={dark ? 1.4 : 1.8}
      />
      <CameraRig />
      <Furniture
        palette={palette}
        onFloorClick={(event) => {
          if (event.delta > 4) return;
          runtime.getState().select(null);
        }}
      />
      <RoomLights palette={palette} onRoomClick={() => actions.openOverview()} />
      <ReceptionDesk palette={palette} />
      <Documents />
      <Kanban palette={palette} />
      <Workstations palette={palette} />
      <Signals palette={palette} />
      <Avatars
        palette={palette}
        onSelect={(id) => {
          const state = runtime.getState();
          state.select(id);
          if (state.camera.follow) state.setCamera({ follow: id });
        }}
      />
      <OverlaySync />
      <PerfMonitor active={active} onSlow={onSlow} />
    </>
  );
}
