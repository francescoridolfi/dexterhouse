// SPDX-License-Identifier: AGPL-3.0-or-later
// Minimap (bottom right): rooms with their colour, agent dots; click to jump there.
import { type MouseEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { roomColor } from "../../theme/tokens.ts";
import { PLAN } from "../rooms/plan.ts";
import { useOffice, useProject } from "../scene/context.ts";

const SCALE = 4;

export function Minimap() {
  const { t } = useTranslation();
  const { runtime, motion } = useOffice();
  const agents = useProject((s) => s.agents);
  const [dots, setDots] = useState<{ id: string; x: number; z: number }[]>([]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setDots([...motion.entries()].map(([id, rt]) => ({ id, x: rt.x, z: rt.z })));
    }, 250);
    return () => window.clearInterval(timer);
  }, [motion]);

  const jump = (event: MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * PLAN.grid.w;
    const z = ((event.clientY - box.top) / box.height) * PLAN.grid.h;
    runtime.getState().setCamera({ target: { x, z }, follow: null });
  };

  return (
    <svg
      role="button"
      aria-label={t("office.minimap")}
      viewBox={`0 0 ${PLAN.grid.w * SCALE} ${PLAN.grid.h * SCALE}`}
      className="absolute right-3 bottom-3 w-40 cursor-pointer rounded-card border border-line bg-surface/90 shadow-card"
      onClick={jump}
    >
      {PLAN.rooms.map((room) => (
        <rect
          key={room.id}
          x={room.rect.x * SCALE + 1}
          y={room.rect.y * SCALE + 1}
          width={Math.min(room.rect.w, PLAN.grid.w - room.rect.x) * SCALE - 2}
          height={Math.min(room.rect.h, PLAN.grid.h - 1 - room.rect.y) * SCALE - 2}
          fill={roomColor(room.id)}
          fillOpacity={0.25}
          stroke={roomColor(room.id)}
          strokeWidth={1.5}
        >
          <title>{t(`room.${room.id}`, { defaultValue: room.id })}</title>
        </rect>
      ))}
      {dots.map((dot) => (
        <circle
          key={dot.id}
          cx={dot.x * SCALE}
          cy={dot.z * SCALE}
          r={3}
          fill="currentColor"
          className="text-text"
        >
          <title>{agents[dot.id]?.displayName ?? dot.id}</title>
        </circle>
      ))}
    </svg>
  );
}
