// SPDX-License-Identifier: AGPL-3.0-or-later
// A glass window: traffic lights, drag by the title bar, resize from the edges, double-click
// to zoom. While dragging only the DOM style changes; the store is updated on release, so
// the page inside (the 3D office too) does not re-render on every pointer move.
import { Minus, Plus, X } from "lucide-react";
import { type PointerEvent, memo, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";

import { useProjectStore } from "../store/projectStore.ts";
import { APPS } from "./apps.ts";
import { WindowBoundary } from "./WindowBoundary.tsx";
import { WindowRoutes } from "./WindowRoutes.tsx";
import { type Rect, type Win, DOCK_RESERVE, MENUBAR_H, clampRect } from "./windowStore.ts";

type Mode = "move" | "e" | "s" | "se" | "w" | "sw";

interface Props {
  win: Win;
  z: number;
  focused: boolean;
  onFocus: () => void;
  onClose: () => void;
  onMinimize: () => void;
  onZoom: () => void;
  onRect: (rect: Rect) => void;
}

const Content = memo(function Content({ path }: { path: string }) {
  return (
    <WindowBoundary path={path}>
      <WindowRoutes location={path} />
    </WindowBoundary>
  );
});

function useTitle(win: Win): string {
  const { t } = useTranslation();
  const projectName = useProjectStore((s) => s.project?.name);
  if (win.app === "project" && projectName) return projectName;
  return t(APPS[win.app].title);
}

function Light({
  color,
  label,
  onClick,
  children,
}: {
  color: string;
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      onDoubleClick={(e) => e.stopPropagation()}
      className={`grid size-3 place-items-center rounded-full shadow-[inset_0_0_0_0.5px_rgb(0_0_0/0.25)] ${color}`}
    >
      <span className="text-black/60 opacity-0 group-hover/lights:opacity-100" aria-hidden>
        {children}
      </span>
    </button>
  );
}

export function Window({ win, z, focused, onFocus, onClose, onMinimize, onZoom, onRect }: Props) {
  const { t } = useTranslation();
  const ref = useRef<HTMLElement>(null);
  const drag = useRef<{ x: number; y: number; rect: Rect; mode: Mode; moved: boolean } | null>(
    null,
  );
  const title = useTitle(win);
  const app = APPS[win.app];
  const Icon = app.icon;
  const content = useMemo(() => <Content path={win.path} />, [win.path]);

  const start = (event: PointerEvent, mode: Mode) => {
    if (event.button !== 0 || !ref.current) return;
    if (mode === "move" && (event.target as HTMLElement).closest("button")) return;
    if (window.innerWidth < 768) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const box = ref.current.getBoundingClientRect();
    let rect: Rect = { x: box.left, y: box.top, w: box.width, h: box.height };
    if (win.maximized && mode === "move") {
      // Leaving the zoomed state keeps the pointer at the same spot of the title bar.
      const restored = win.rect;
      rect = { ...restored, x: event.clientX - restored.w / 2, y: box.top };
    }
    drag.current = { x: event.clientX, y: event.clientY, rect, mode, moved: false };
  };

  const move = (event: PointerEvent) => {
    const state = drag.current;
    const el = ref.current;
    if (!state || !el) return;
    const dx = event.clientX - state.x;
    const dy = event.clientY - state.y;
    if (!state.moved && Math.abs(dx) + Math.abs(dy) < 3) return;
    state.moved = true;
    const r = { ...state.rect };
    // Edges are single letters ("e", "sw"…): never test "move" for letters.
    const edges = state.mode === "move" ? "" : state.mode;
    if (state.mode === "move") {
      r.x += dx;
      r.y += dy;
    }
    if (edges.includes("e")) r.w += dx;
    if (edges.includes("s")) r.h += dy;
    if (edges.includes("w")) {
      r.w -= dx;
      r.x += dx;
    }
    const c = clampRect(r);
    if (edges.includes("w")) c.x = state.rect.x + state.rect.w - c.w;
    Object.assign(el.style, {
      left: `${c.x}px`,
      top: `${c.y}px`,
      width: `${c.w}px`,
      height: `${c.h}px`,
      right: "auto",
      bottom: "auto",
    });
    el.dataset.rect = JSON.stringify(c);
  };

  const end = () => {
    const state = drag.current;
    drag.current = null;
    const raw = ref.current?.dataset.rect;
    if (state?.moved && raw) onRect(JSON.parse(raw) as Rect);
  };

  const geometry = win.maximized
    ? { left: 8, top: MENUBAR_H + 6, right: 8, bottom: DOCK_RESERVE }
    : { left: win.rect.x, top: win.rect.y, width: win.rect.w, height: win.rect.h };

  const handle = (mode: Mode, className: string) => (
    <div
      aria-hidden
      className={`absolute z-10 max-md:hidden ${className}`}
      onPointerDown={(e) => start(e, mode)}
      onPointerMove={move}
      onPointerUp={end}
    />
  );

  return (
    <section
      ref={ref}
      aria-label={title}
      data-app={win.app}
      data-focused={focused || undefined}
      onPointerDownCapture={focused ? undefined : onFocus}
      style={{ ...geometry, zIndex: z }}
      className={`os-window-in absolute flex flex-col rounded-[18px] transition-[opacity,transform,visibility] duration-300 ease-(--ease-dh) max-md:inset-x-0! max-md:top-8! max-md:bottom-[88px]! max-md:h-auto! max-md:w-auto! max-md:rounded-none ${
        win.minimized
          ? "pointer-events-none invisible translate-y-[45vh] scale-[0.2] opacity-0"
          : "visible"
      }`}
    >
      <div
        aria-hidden
        className={`glass-strong glass-rim absolute inset-0 rounded-[inherit] ${focused ? "" : "glass-inactive"}`}
      />
      <header
        className="relative flex h-11 shrink-0 cursor-default items-center px-4 select-none"
        onPointerDown={(e) => start(e, "move")}
        onPointerMove={move}
        onPointerUp={end}
        onDoubleClick={onZoom}
      >
        <div className={`group/lights flex items-center gap-2 ${focused ? "" : "grayscale"}`}>
          <Light color="bg-[#ff5f57]" label={t("os.window.close")} onClick={onClose}>
            <X className="size-2" strokeWidth={3} />
          </Light>
          <Light color="bg-[#febc2e]" label={t("os.window.minimize")} onClick={onMinimize}>
            <Minus className="size-2" strokeWidth={3} />
          </Light>
          <Light color="bg-[#28c840]" label={t("os.window.zoom")} onClick={onZoom}>
            <Plus className="size-2" strokeWidth={3} />
          </Light>
        </div>
        <div
          className={`pointer-events-none absolute inset-x-24 flex items-center justify-center gap-2 text-[13px] font-semibold ${focused ? "text-fg" : "text-muted"}`}
        >
          <Icon aria-hidden className="size-3.5 opacity-70" />
          <span className="truncate">{title}</span>
        </div>
      </header>
      <div className="@container relative min-h-0 flex-1 overflow-auto rounded-b-[inherit] px-5 pt-1 pb-5">
        {content}
      </div>
      {handle("e", "top-3 -right-1 bottom-3 w-2 cursor-ew-resize")}
      {handle("w", "top-3 -left-1 bottom-3 w-2 cursor-ew-resize")}
      {handle("s", "right-3 -bottom-1 left-3 h-2 cursor-ns-resize")}
      {handle("se", "-right-1 -bottom-1 size-4 cursor-nwse-resize")}
      {handle("sw", "-bottom-1 -left-1 size-4 cursor-nesw-resize")}
    </section>
  );
}
