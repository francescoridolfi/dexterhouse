// SPDX-License-Identifier: AGPL-3.0-or-later
// Replay playback: loads the events (or a clip), rebuilds the scene from an empty store and
// plays it at 1×–20×. The office runtime and a private project store receive the frames.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createStore } from "zustand/vanilla";

import type { EventEnvelope, Project } from "../../api/types.ts";
import { type ProjectState, emptyState } from "../../store/model.ts";
import type { AvatarRuntime } from "../avatars/motion.ts";
import type { OfficeRuntimeStore } from "../scene/runtime.ts";
import { settle } from "../state/reducer.ts";
import { type Clip, downloadClip, makeClip } from "./clip.ts";
import { type Frame, ReplayEngine, emptyReplayState, stepProject } from "./engine.ts";
import { loadEvents } from "./loadEvents.ts";
import { type Timeline, buildTimeline, countAt, nextGate, timeAtWall } from "./timeline.ts";

export const SPEEDS = [1, 2, 5, 10, 20] as const;

export interface ReplayUi {
  status: "off" | "loading" | "ready" | "error";
  loaded: number;
  error: string | null;
  position: number;
  duration: number;
  playing: boolean;
  speed: number;
  marks: { in: number | null; out: number | null };
  gates: number[];
}

const OFF: ReplayUi = {
  status: "off",
  loaded: 0,
  error: null,
  position: 0,
  duration: 0,
  playing: false,
  speed: 1,
  marks: { in: null, out: null },
  gates: [],
};

export function useReplay(
  projectId: string,
  project: Project | null,
  runtime: OfficeRuntimeStore,
  motion: Map<string, AvatarRuntime>,
) {
  const store = useMemo(() => createStore<ProjectState>(() => emptyState(projectId)), [projectId]);
  const [ui, setUi] = useState<ReplayUi>(OFF);
  const engine = useRef<ReplayEngine | null>(null);
  const frame = useRef<Frame | null>(null);
  const position = useRef(0);
  const speed = useRef(1);
  const abort = useRef<AbortController | null>(null);

  const clock = useCallback(() => position.current, []);
  const timeScale = useCallback(() => speed.current, []);
  const wallTime = useCallback(() => {
    const tl = engine.current?.timeline;
    const count = frame.current?.count ?? 0;
    return tl && count > 0 ? tl.wall[count - 1]! : Date.now();
  }, []);

  const seek = useCallback(
    (t: number) => {
      const current = engine.current;
      if (!current) return;
      const tl = current.timeline;
      position.current = Math.max(0, Math.min(t, tl.duration));
      const next = current.frameAt(countAt(tl, position.current));
      frame.current = next;
      store.setState(next.project, true);
      motion.clear();
      runtime.getState().replace(settle(next.office));
      setUi((u) => ({ ...u, position: position.current }));
    },
    [motion, runtime, store],
  );

  const open = useCallback(
    (events: EventEnvelope[], startWall: number | null) => {
      const tl: Timeline = buildTimeline(events);
      engine.current = new ReplayEngine(tl, emptyReplayState(projectId, project));
      setUi({
        ...OFF,
        status: "ready",
        loaded: events.length,
        duration: tl.duration,
        gates: tl.gates.map((i) => tl.times[i]!),
      });
      seek(startWall === null ? 0 : timeAtWall(tl, startWall));
    },
    [projectId, project, seek],
  );

  const start = useCallback(
    (startWall: number | null = null) => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setUi({ ...OFF, status: "loading" });
      loadEvents(
        projectId,
        new Date().toISOString(),
        (loaded) => setUi((u) => ({ ...u, loaded })),
        controller.signal,
      )
        .then((events) => {
          if (!controller.signal.aborted) open(events, startWall);
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) setUi({ ...OFF, status: "error", error: String(error) });
        });
    },
    [open, projectId],
  );

  const startClip = useCallback(
    (clip: Clip) => open(clip.events, Date.parse(clip.start_at)),
    [open],
  );

  const stop = useCallback(() => {
    abort.current?.abort();
    engine.current = null;
    frame.current = null;
    motion.clear();
    setUi(OFF);
  }, [motion]);

  // Playback loop: events up to the playback time go through the same reducers.
  useEffect(() => {
    if (!ui.playing) return;
    let last = performance.now();
    let raf = 0;
    let shown = 0;
    const loop = (nowMs: number) => {
      const current = engine.current;
      const at = frame.current;
      if (!current || !at) return;
      const tl = current.timeline;
      position.current = Math.min(tl.duration, position.current + (nowMs - last) * speed.current);
      last = nowMs;
      const target = countAt(tl, position.current);
      let project = at.project;
      let count = at.count;
      while (count < target) {
        const event = tl.events[count]!;
        project = stepProject(project, event);
        runtime.getState().apply(event, project, tl.times[count]!);
        count += 1;
      }
      if (count !== at.count) {
        frame.current = { project, office: runtime.getState().model, count };
        store.setState(project, true);
      }
      const ended = position.current >= tl.duration;
      if (ended || nowMs - shown > 100) {
        shown = nowMs;
        setUi((u) => ({ ...u, position: position.current, playing: !ended }));
      }
      if (!ended) raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [ui.playing, runtime, store]);

  useEffect(() => () => abort.current?.abort(), []);

  const controls = {
    start,
    startClip,
    stop,
    seek,
    play: () => {
      if (position.current >= ui.duration) seek(0);
      setUi((u) => ({ ...u, playing: true }));
    },
    jumpGate: (direction: 1 | -1) => {
      const tl = engine.current?.timeline;
      const at = tl ? nextGate(tl, position.current, direction) : null;
      if (at !== null) seek(at);
    },
    pause: () => setUi((u) => ({ ...u, playing: false })),
    setSpeed: (value: number) => {
      speed.current = value;
      setUi((u) => ({ ...u, speed: value }));
    },
    mark: (which: "in" | "out") =>
      setUi((u) => ({ ...u, marks: { ...u.marks, [which]: position.current } })),
    exportClip: () => {
      const tl = engine.current?.timeline;
      if (!tl || tl.events.length === 0) return;
      const from = countAt(tl, ui.marks.in ?? 0);
      const to = countAt(tl, ui.marks.out ?? tl.duration);
      downloadClip(
        makeClip(
          { id: projectId, name: project?.name ?? projectId },
          tl.events,
          Math.max(0, Math.min(from, to) - 1),
          Math.max(from, to) - 1,
        ),
      );
    },
  };
  return { ui, store, clock, wallTime, timeScale, controls };
}
