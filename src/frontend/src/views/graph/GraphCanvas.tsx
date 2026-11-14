// SPDX-License-Identifier: AGPL-3.0-or-later
// Canvas 2D renderer of the code graph: drag the background to pan, the wheel to zoom,
// drag a node to pin it; click selects, double-click (or ⌘/Ctrl-click) opens it in Code.
// Canvas, not SVG: thousands of nodes stay fluid, and nothing touches the CSP (no styles).
import { type LucideIcon, Maximize, Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { ForceLayout } from "./forceLayout.ts";
import type { GraphEdge, GraphNode } from "./graphModel.ts";
import { RADIUS, type View, fitTransform, paint } from "./paint.ts";

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selected: string | null;
  matches: Set<string>;
  focus: { id: string; seq: number } | null;
  onSelect: (id: string | null) => void;
  onOpen: (node: GraphNode) => void;
  className?: string;
}

const EMPTY = new ForceLayout([], []);

function ZoomButton({
  label,
  icon: Icon,
  onClick,
}: {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="grid size-8 place-items-center text-muted hover:bg-white/10 hover:text-fg"
    >
      <Icon aria-hidden className="size-3.5" />
    </button>
  );
}

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function GraphCanvas({
  nodes,
  edges,
  selected,
  matches,
  focus,
  onSelect,
  onOpen,
  className = "",
}: Props) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const view = useRef<View>({ x: 0, y: 0, k: 1 });
  const size = useRef({ w: 0, h: 0 });
  /** The view follows the layout and the canvas size until the user pans or zooms. */
  const auto = useRef(true);
  const frame = useRef(0);

  const layoutRef = useRef<ForceLayout>(EMPTY);
  const state = useRef({ selected, matches, nodes, edges, layout: EMPTY });

  useLayoutEffect(() => {
    state.current = { ...state.current, selected, matches, nodes, edges };
  });

  const draw = useCallback(() => {
    const el = canvas.current;
    const ctx = el?.getContext?.("2d");
    if (!el || !ctx) return;
    const s = state.current;
    if (auto.current && s.layout.alpha < 0.08 && size.current.w > 0) {
      view.current = fitTransform(s.layout.nodes, size.current.w, size.current.h);
    }
    paint(ctx, size.current, view.current, s);
  }, []);

  const animate = useCallback(() => {
    cancelAnimationFrame(frame.current);
    const step = () => {
      const l = state.current.layout;
      const ticks = l.nodes.length > 2000 ? 1 : 2;
      for (let i = 0; i < ticks && !l.settled; i += 1) l.tick();
      draw();
      if (!l.settled) frame.current = requestAnimationFrame(step);
    };
    if (reducedMotion()) {
      state.current.layout.run(300);
      draw();
    } else frame.current = requestAnimationFrame(step);
  }, [draw]);

  useEffect(() => {
    const index = new Map(nodes.map((n, i) => [n.id, i]));
    const links = edges.map((e) => ({
      source: index.get(e.source)!,
      target: index.get(e.target)!,
    }));
    const next = new ForceLayout(
      nodes.map((n) => n.id),
      links,
    );
    const old = layoutRef.current;
    if (old.nodes.length > 0) {
      const at = new Map(old.nodes.map((n) => [n.id, n]));
      for (const n of next.nodes) {
        const p = at.get(n.id);
        if (p) Object.assign(n, { x: p.x, y: p.y });
      }
      next.alpha = 0.5;
    } else auto.current = true;
    layoutRef.current = next;
    state.current = { ...state.current, nodes, edges, layout: next };
    animate();
    return () => cancelAnimationFrame(frame.current);
  }, [nodes, edges, animate]);

  useEffect(draw, [draw, selected, matches]);

  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const c = canvas.current;
      if (!entry || !c) return;
      const { width, height } = entry.contentRect;
      const dpr = window.devicePixelRatio || 1;
      if (size.current.w === 0) view.current = { x: width / 2, y: height / 2, k: 1 };
      size.current = { w: width, h: height };
      c.width = Math.round(width * dpr);
      c.height = Math.round(height * dpr);
      draw();
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [draw]);

  useEffect(() => {
    if (!focus) return;
    const n = layoutRef.current.nodes.find((node) => node.id === focus.id);
    if (!n) return;
    const k = Math.max(view.current.k, 1.4);
    view.current = { k, x: size.current.w / 2 - n.x * k, y: size.current.h / 2 - n.y * k };
    auto.current = false;
    draw();
  }, [focus, draw]);

  const toWorld = (cx: number, cy: number) => {
    const rect = canvas.current!.getBoundingClientRect();
    const v = view.current;
    return { x: (cx - rect.left - v.x) / v.k, y: (cy - rect.top - v.y) / v.k };
  };

  const zoom = useCallback(
    (factor: number, cx = size.current.w / 2, cy = size.current.h / 2) => {
      const v = view.current;
      const k = Math.min(8, Math.max(0.05, v.k * factor));
      view.current = { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
      auto.current = false;
      draw();
    },
    [draw],
  );

  const zoomIn = useCallback(() => zoom(1.3), [zoom]);
  const zoomOut = useCallback(() => zoom(1 / 1.3), [zoom]);
  const fit = useCallback(() => {
    auto.current = true;
    view.current = fitTransform(layoutRef.current.nodes, size.current.w, size.current.h);
    draw();
  }, [draw]);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      zoom(Math.exp(-event.deltaY * 0.0015), event.clientX - rect.left, event.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoom]);

  const drag = useRef<{
    node: number;
    sx: number;
    sy: number;
    vx: number;
    vy: number;
    moved: boolean;
  } | null>(null);

  const hit = (cx: number, cy: number) => {
    const p = toWorld(cx, cy);
    return layoutRef.current.find(p.x, p.y, ((RADIUS.file ?? 6) + 4) / Math.min(view.current.k, 1));
  };

  return (
    <div
      ref={box}
      className={`relative overflow-hidden rounded-[14px] border border-white/8 bg-[#0b0d12] ${className}`}
    >
      <canvas
        ref={canvas}
        role="img"
        aria-label={t("graph.canvasLabel", { nodes: nodes.length, edges: edges.length })}
        className="absolute inset-0 size-full touch-none"
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = {
            node: hit(event.clientX, event.clientY),
            sx: event.clientX,
            sy: event.clientY,
            vx: view.current.x,
            vy: view.current.y,
            moved: false,
          };
        }}
        onPointerMove={(event) => {
          const d = drag.current;
          if (!d) return;
          const dx = event.clientX - d.sx;
          const dy = event.clientY - d.sy;
          if (!d.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
          d.moved = true;
          if (d.node >= 0) {
            const p = toWorld(event.clientX, event.clientY);
            const n = layoutRef.current.nodes[d.node]!;
            n.fx = p.x;
            n.fy = p.y;
            layoutRef.current.reheat(0.2);
            auto.current = false;
            animate();
          } else {
            view.current = { ...view.current, x: d.vx + dx, y: d.vy + dy };
            auto.current = false;
            draw();
          }
        }}
        onPointerUp={(event) => {
          const d = drag.current;
          drag.current = null;
          if (!d) return;
          if (d.node >= 0) {
            const n = layoutRef.current.nodes[d.node]!;
            n.fx = null;
            n.fy = null;
          }
          if (d.moved) return;
          const node = d.node >= 0 ? nodes[d.node] : undefined;
          if (node && (event.metaKey || event.ctrlKey)) onOpen(node);
          else onSelect(node?.id ?? null);
        }}
        onDoubleClick={(event) => {
          const i = hit(event.clientX, event.clientY);
          if (i >= 0) onOpen(nodes[i]!);
        }}
      />
      <div className="absolute right-2 bottom-2 flex flex-col overflow-hidden rounded-[10px] border border-white/10 bg-black/50 backdrop-blur">
        <ZoomButton label={t("graph.zoomIn")} icon={Plus} onClick={zoomIn} />
        <ZoomButton label={t("graph.zoomOut")} icon={Minus} onClick={zoomOut} />
        <ZoomButton label={t("graph.fit")} icon={Maximize} onClick={fit} />
      </div>
    </div>
  );
}
