// SPDX-License-Identifier: AGPL-3.0-or-later
// Glass dock with macOS-style magnification. Pinned apps first; open windows of the other
// apps after a separator. A dot marks a running app, a red badge the open decisions.
import { type MouseEvent, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useOpenGates } from "../api/queries.ts";
import { APPS, type AppId, DOCK } from "./apps.ts";
import { useWindows } from "./context.ts";

const BASE = 50;
const REACH = 140;
const GROW = 0.5;

function Tile({
  app,
  scale = 1,
  running,
  badge,
}: {
  app: AppId;
  scale?: number;
  running: boolean;
  badge: number;
}) {
  const { t } = useTranslation();
  const path = useWindows((s) => s.windows[app]?.path) ?? APPS[app].defaultPath;
  const def = APPS[app];
  const Icon = def.icon;
  const size = BASE * scale;
  const label = t(def.title);
  return (
    <Link
      to={path}
      data-tile={app}
      aria-label={label}
      className="group relative flex flex-col items-center outline-none max-md:scale-90"
      style={{ width: size }}
    >
      <span className="glass pointer-events-none absolute -top-11 rounded-lg px-2.5 py-1 text-xs whitespace-nowrap opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
        {label}
      </span>
      <span
        className="relative grid place-items-center rounded-[26%] shadow-[0_6px_14px_-4px_rgb(0_0_0/0.6),inset_0_1px_0_rgb(255_255_255/0.35),inset_0_-2px_4px_rgb(0_0_0/0.2)] transition-[width,height] duration-150 ease-out group-focus-visible:ring-2 group-focus-visible:ring-accent group-active:brightness-75"
        style={{
          width: size,
          height: size,
          background: `linear-gradient(160deg, ${def.tint[0]}, ${def.tint[1]})`,
        }}
      >
        <span className="absolute inset-x-[8%] top-[5%] h-[45%] rounded-[40%] bg-gradient-to-b from-white/30 to-white/0" />
        <Icon
          aria-hidden
          className="relative text-white drop-shadow"
          style={{ width: size * 0.48, height: size * 0.48 }}
          strokeWidth={1.9}
        />
        {badge > 0 ? (
          <span className="absolute -top-1 -right-1 grid min-w-5 place-items-center rounded-full bg-[#ff453a] px-1 text-[11px] leading-5 font-bold text-white shadow">
            {badge}
          </span>
        ) : null}
      </span>
      <span
        aria-hidden
        className={`mt-1 size-1 rounded-full bg-white/80 ${running ? "opacity-100" : "opacity-0"}`}
      />
    </Link>
  );
}

export function Dock() {
  const { t } = useTranslation();
  const nav = useRef<HTMLElement>(null);
  const [scales, setScales] = useState<Record<string, number>>({});
  const order = useWindows((s) => s.order);
  const gates = useOpenGates();
  const inbox = gates.data?.results.length ?? 0;
  const extra = order.filter((id) => !DOCK.includes(id));
  const onMove = (event: MouseEvent) => {
    if (window.matchMedia?.("(hover: hover)").matches === false) return;
    const next: Record<string, number> = {};
    nav.current?.querySelectorAll<HTMLElement>("[data-tile]").forEach((tile) => {
      const box = tile.getBoundingClientRect();
      const distance = Math.abs(event.clientX - (box.left + box.width / 2));
      next[tile.dataset.tile ?? ""] = 1 + GROW * Math.max(0, 1 - distance / REACH) ** 2;
    });
    setScales(next);
  };

  return (
    <nav
      data-dock
      aria-label={t("os.dock")}
      onMouseMove={onMove}
      ref={nav}
      onMouseLeave={() => setScales({})}
      className="glass glass-rim fixed bottom-2 left-1/2 z-[1000] flex -translate-x-1/2 items-end gap-2 rounded-[24px] px-2.5 pt-2.5 pb-1"
    >
      {DOCK.map((app) => (
        <Tile
          key={app}
          app={app}
          scale={scales[app]}
          running={order.includes(app)}
          badge={app === "inbox" ? inbox : 0}
        />
      ))}
      <span aria-hidden className="mx-1 mb-3 h-10 w-px self-center bg-white/15" />
      <Tile
        app="newProject"
        scale={scales.newProject}
        running={order.includes("newProject")}
        badge={0}
      />
      {extra
        .filter((app) => app !== "newProject")
        .map((app) => (
          <Tile key={app} app={app} scale={scales[app]} running badge={0} />
        ))}
    </nav>
  );
}
