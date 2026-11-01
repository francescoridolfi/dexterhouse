// SPDX-License-Identifier: AGPL-3.0-or-later
// Bottom bar of the Office tab in replay: time slider with gate markers, 1×–20×, jump to
// gates, in/out marks, clip export and import.
import { BellRing, Download, FileUp, Pause, Play, SkipBack, SkipForward, X } from "lucide-react";
import { type ChangeEvent, useRef } from "react";
import { useTranslation } from "react-i18next";

import { toastError } from "../../components/toastStore.ts";
import { dateTime } from "../../utils/format.ts";
import { parseClip } from "./clip.ts";
import { SPEEDS, type useReplay } from "./useReplay.ts";

type Replay = ReturnType<typeof useReplay>;

const button =
  "grid size-9 shrink-0 place-items-center rounded-card hover:bg-bg disabled:opacity-40";

export function ReplayBar({ replay }: { replay: Replay }) {
  const { t } = useTranslation();
  const { ui, controls, wallTime } = replay;
  const file = useRef<HTMLInputElement>(null);
  const ready = ui.status === "ready";
  const pct = (time: number) => `${ui.duration ? (time / ui.duration) * 100 : 0}%`;
  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    event.target.value = "";
    if (!chosen) return;
    void chosen
      .text()
      .then((text) => controls.startClip(parseClip(text)))
      .catch((error: unknown) => toastError(t("office.replay.badClip"), error));
  };

  return (
    <div
      role="group"
      aria-label={t("office.replay.title")}
      className="flex flex-wrap items-center gap-1 border-t border-line bg-surface px-2 py-2 text-sm"
    >
      {ui.status === "loading" ? (
        <p role="status" className="flex-1">
          {t("office.replay.loading", { count: ui.loaded })}
        </p>
      ) : ui.status === "error" ? (
        <p role="alert" className="flex-1 text-failed">
          {t("office.replay.failed")}
        </p>
      ) : (
        <>
          <button
            type="button"
            className={button}
            disabled={!ready}
            aria-label={ui.playing ? t("office.replay.pause") : t("office.replay.play")}
            onClick={ui.playing ? controls.pause : controls.play}
          >
            {ui.playing ? (
              <Pause aria-hidden className="size-4" />
            ) : (
              <Play aria-hidden className="size-4" />
            )}
          </button>
          <button
            type="button"
            className={button}
            aria-label={t("office.replay.prevGate")}
            onClick={() => controls.jumpGate(-1)}
          >
            <SkipBack aria-hidden className="size-4" />
          </button>
          <button
            type="button"
            className={button}
            aria-label={t("office.replay.nextGate")}
            onClick={() => controls.jumpGate(1)}
          >
            <SkipForward aria-hidden className="size-4" />
          </button>
          <div className="relative min-w-24 flex-1">
            <input
              type="range"
              min={0}
              max={Math.max(1, Math.round(ui.duration))}
              step={100}
              value={Math.round(ui.position)}
              aria-label={t("office.replay.position")}
              aria-valuetext={dateTime(new Date(wallTime()).toISOString())}
              onChange={(e) => controls.seek(Number(e.target.value))}
              className="w-full accent-accent"
            />
            {ui.gates.map((gate, i) => (
              <button
                key={`${gate}-${i}`}
                type="button"
                title={t("office.replay.gate")}
                aria-label={t("office.replay.gateAt", { n: i + 1 })}
                onClick={() => controls.seek(gate)}
                className="absolute -top-2 -translate-x-1/2 text-blocked"
                style={{ left: pct(gate) }}
              >
                <BellRing aria-hidden className="size-3" />
              </button>
            ))}
          </div>
          <time className="hidden w-32 font-mono text-xs text-muted xl:block">
            {dateTime(new Date(wallTime()).toISOString())}
          </time>
          <select
            aria-label={t("office.replay.speed")}
            value={ui.speed}
            onChange={(e) => controls.setSpeed(Number(e.target.value))}
            className="min-h-9 rounded-card border border-line bg-surface px-1"
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
          <button
            type="button"
            className="min-h-9 rounded-card px-2 hover:bg-bg"
            onClick={() => controls.mark("in")}
          >
            {t("office.replay.markIn")}
          </button>
          <button
            type="button"
            className="min-h-9 rounded-card px-2 hover:bg-bg"
            onClick={() => controls.mark("out")}
          >
            {t("office.replay.markOut")}
          </button>
          <button
            type="button"
            className={button}
            aria-label={t("office.replay.export")}
            title={t("office.replay.export")}
            onClick={controls.exportClip}
          >
            <Download aria-hidden className="size-4" />
          </button>
        </>
      )}
      <button
        type="button"
        className={button}
        aria-label={t("office.replay.import")}
        title={t("office.replay.import")}
        onClick={() => file.current?.click()}
      >
        <FileUp aria-hidden className="size-4" />
      </button>
      <input
        ref={file}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={onFile}
      />
      <button
        type="button"
        className={button}
        aria-label={t("office.replay.close")}
        onClick={controls.stop}
      >
        <X aria-hidden className="size-4" />
      </button>
    </div>
  );
}
