// SPDX-License-Identifier: AGPL-3.0-or-later
// Camera buttons (same as the keys), fast mode and the replay switch.
import { Crosshair, History, RotateCcw, RotateCw, Rabbit, ZoomIn, ZoomOut } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useOffice, useRuntime } from "../scene/context.ts";
import { followSelected, rotateBy, zoomBy } from "../scene/useControls.ts";

function Tool({
  label,
  onClick,
  pressed,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  pressed?: boolean;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={`grid size-9 place-items-center rounded-card hover:bg-bg disabled:opacity-40 ${
        pressed ? "bg-accent/15 text-accent" : ""
      }`}
    >
      {children}
    </button>
  );
}

export function Toolbar({ onReplay, replaying }: { onReplay: () => void; replaying: boolean }) {
  const { t } = useTranslation();
  const { runtime } = useOffice();
  const fast = useRuntime((s) => s.fast);
  const selected = useRuntime((s) => s.selected);
  const follow = useRuntime((s) => s.camera.follow);
  const icon = "size-4";
  return (
    <div
      role="toolbar"
      aria-label={t("office.toolbar")}
      className="absolute top-3 left-3 flex gap-0.5 rounded-card border border-line bg-surface/95 p-1 shadow-card"
    >
      <Tool label={t("office.rotateLeft")} onClick={() => rotateBy(runtime, -1)}>
        <RotateCcw aria-hidden className={icon} />
      </Tool>
      <Tool label={t("office.rotateRight")} onClick={() => rotateBy(runtime, 1)}>
        <RotateCw aria-hidden className={icon} />
      </Tool>
      <Tool label={t("office.zoomIn")} onClick={() => zoomBy(runtime, 1)}>
        <ZoomIn aria-hidden className={icon} />
      </Tool>
      <Tool label={t("office.zoomOut")} onClick={() => zoomBy(runtime, -1)}>
        <ZoomOut aria-hidden className={icon} />
      </Tool>
      <Tool
        label={t("office.follow")}
        pressed={!!follow}
        disabled={!selected}
        onClick={() => followSelected(runtime)}
      >
        <Crosshair aria-hidden className={icon} />
      </Tool>
      <Tool
        label={t("office.fast")}
        pressed={fast}
        onClick={() => runtime.getState().setFast(!fast)}
      >
        <Rabbit aria-hidden className={icon} />
      </Tool>
      <Tool label={t("office.replay.toggle")} pressed={replaying} onClick={onReplay}>
        <History aria-hidden className={icon} />
      </Tool>
    </div>
  );
}
