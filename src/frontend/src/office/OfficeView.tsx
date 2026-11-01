// SPDX-License-Identifier: AGPL-3.0-or-later
// The 3D office (lazy chunk, loaded only from the Office tab): canvas, overlay, replay bar and
// the agent side panel (480 px, the scene shrinks). Reads only from the stores.
import { Canvas } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useStore } from "zustand";
import type { StoreApi } from "zustand/vanilla";

import type { ProjectState } from "../store/model.ts";
import { useProjectStore } from "../store/projectStore.ts";
import { officeDescription } from "../store/selectors.ts";
import { ArtifactDrawer } from "../views/project/panels/ArtifactDrawer.tsx";
import { TaskDrawer } from "../views/project/panels/TaskDrawer.tsx";
import { TurnDrawer } from "../views/project/panels/TurnDrawer.tsx";
import type { AvatarRuntime } from "./avatars/motion.ts";
import { Labels } from "./overlay/Labels.tsx";
import { Minimap } from "./overlay/Minimap.tsx";
import { Toolbar } from "./overlay/Toolbar.tsx";
import { Tooltip } from "./overlay/Tooltip.tsx";
import { registerOfficeStrings } from "./i18n.ts";
import { ReplayBar } from "./replay/ReplayBar.tsx";
import { useReplay } from "./replay/useReplay.ts";
import { initialRoom } from "./rooms/roomFor.ts";
import { AgentSidePanel } from "./scene/AgentSidePanel.tsx";
import { OfficeContext, type OfficeContextValue } from "./scene/context.ts";
import { createOfficeRuntime } from "./scene/runtime.ts";
import { Scene } from "./scene/Scene.tsx";
import { Throttle } from "./scene/Throttle.tsx";
import { useControls } from "./scene/useControls.ts";
import { useLiveFeed } from "./scene/useLiveFeed.ts";
import { usePageVisible, useReducedMotion } from "./utils/media.ts";

export interface OfficeViewProps {
  /** The Office tab is the visible tab (otherwise the scene renders at 5 fps). */
  active: boolean;
  onSlow: () => void;
  onOpenGate: (gateId: string) => void;
  /** Wall time (ms) to open the replay at, from a Log row. */
  replayAt: number | null;
}

registerOfficeStrings();

const liveStore = useProjectStore as unknown as StoreApi<ProjectState>;
const liveClock = () => performance.now();
const liveWall = () => Date.now();
const one = () => 1;

export default function OfficeView({ active, onSlow, onOpenGate, replayAt }: OfficeViewProps) {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const visible = usePageVisible();
  const runtime = useMemo(() => createOfficeRuntime(reduced), [reduced]);
  const motion = useMemo(() => new Map<string, AvatarRuntime>(), []);
  const labels = useMemo(() => new Map<string, HTMLElement>(), []);
  const projectId = useProjectStore((s) => s.projectId ?? "");
  const project = useProjectStore((s) => s.project);
  const replay = useReplay(projectId, project, runtime, motion);
  const replaying = replay.ui.status !== "off";
  const container = useRef<HTMLDivElement>(null);
  const [artifact, setArtifact] = useState<string | null>(null);
  const [task, setTask] = useState<string | null>(null);
  const [turn, setTurn] = useState<string | null>(null);

  useLiveFeed(runtime, !replaying, liveClock);
  useControls(container, runtime, active);
  useEffect(() => {
    runtime.getState().frameRoom(initialRoom(useProjectStore.getState()));
  }, [runtime]);
  const { start } = replay.controls;
  useEffect(() => {
    if (replayAt !== null) start(replayAt);
  }, [replayAt, start]);

  const openCosts = useCallback(
    () => void navigate(`/projects/${projectId}/costs`),
    [navigate, projectId],
  );
  const value: OfficeContextValue = useMemo(
    () => ({
      project: replaying ? replay.store : liveStore,
      runtime,
      motion,
      labels,
      clock: replaying ? replay.clock : liveClock,
      wallTime: replaying ? replay.wallTime : liveWall,
      timeScale: replaying ? replay.timeScale : one,
      replay: replaying,
      actions: {
        openGate: onOpenGate,
        openCosts,
        openArtifact: setArtifact,
        openTask: setTask,
        openPackages: () => void navigate("/packages"),
        openOverview: () => void navigate(`/projects/${projectId}`),
      },
    }),
    [
      replaying,
      replay.store,
      replay.clock,
      replay.wallTime,
      replay.timeScale,
      runtime,
      motion,
      labels,
      onOpenGate,
      openCosts,
      navigate,
      projectId,
    ],
  );
  const description = useStore(value.project, officeDescription);
  const frameloop = !visible ? "never" : active ? "always" : "demand";

  return (
    <OfficeContext.Provider value={value}>
      <div className="flex h-[70vh] min-h-[28rem] overflow-hidden rounded-card border border-line bg-surface">
        <div className="flex min-w-0 flex-1 flex-col">
          <div ref={container} className="relative min-h-0 flex-1 touch-none select-none">
            <div role="img" aria-label={description} className="absolute inset-0">
              <Canvas
                orthographic
                frameloop={frameloop}
                dpr={[1, 1.5]}
                camera={{ position: [60, 46, 60], zoom: 12, near: 0.1, far: 400 }}
                gl={{ antialias: true, powerPreference: "high-performance" }}
                data-testid="office-canvas"
              >
                <OfficeContext.Provider value={value}>
                  <Scene active={active && visible} onSlow={onSlow} />
                  <Throttle running={visible && !active} fps={5} />
                </OfficeContext.Provider>
              </Canvas>
            </div>
            <Labels />
            <Toolbar
              replaying={replaying}
              onReplay={() => (replaying ? replay.controls.stop() : replay.controls.start())}
            />
            <Minimap />
            <Tooltip />
          </div>
          {replaying ? <ReplayBar replay={replay} /> : null}
        </div>
        <AgentSidePanel onOpenTurn={setTurn} />
      </div>
      {artifact ? <ArtifactDrawer artifactId={artifact} onClose={() => setArtifact(null)} /> : null}
      {task ? <TaskDrawer taskId={task} onClose={() => setTask(null)} /> : null}
      {turn ? <TurnDrawer turnId={turn} onClose={() => setTurn(null)} /> : null}
    </OfficeContext.Provider>
  );
}
