// SPDX-License-Identifier: AGPL-3.0-or-later
// DOM layer over the canvas: name and role above each head, state and tool icons, alarm,
// speech bubble (≤ 120 chars, refreshed twice a second). Positions come from OverlaySync.
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { BREAK_ROOM_LIMIT } from "../avatars/visible.ts";
import { useOffice, useProject, useRuntime } from "../scene/context.ts";
import { MODE_EMOJI, TOOL_EMOJI, avatarMode } from "../state/mode.ts";

const BUBBLE_CHARS = 120;
const QUIET_MS = 2_000;

function bubbleText(text: string): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > BUBBLE_CHARS ? `…${flat.slice(-BUBBLE_CHARS + 1)}` : flat;
}

export function Labels() {
  const { t } = useTranslation();
  const { labels, clock, replay, project } = useOffice();
  const avatars = useRuntime((s) => s.model.avatars);
  const fast = useRuntime((s) => s.fast);
  const selected = useRuntime((s) => s.selected);
  const agents = useProject((s) => s.agents);
  const heard = useRef(new Map<string, { seq: number; at: number }>());
  // Timers and live speech are sampled twice a second (bubble text at most 2 updates/s).
  const [frame, setFrame] = useState<{ now: number; live: Record<string, string> }>({
    now: 0,
    live: {},
  });

  useEffect(() => {
    const sample = () => {
      const now = clock();
      const live: Record<string, string> = {};
      for (const speech of Object.values(project.getState().speaking)) {
        const seen = heard.current.get(speech.agentId);
        if (!seen || seen.seq !== speech.seq) {
          heard.current.set(speech.agentId, { seq: speech.seq, at: now });
        }
        if (now - (heard.current.get(speech.agentId)?.at ?? 0) < QUIET_MS) {
          live[speech.agentId] = speech.text;
        }
      }
      setFrame({ now, live });
    };
    const first = window.setTimeout(sample, 0);
    const timer = window.setInterval(sample, 500);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [clock, project]);

  const resting = useMemo(
    () => Object.values(avatars).filter((a) => a.room === "break_room" && !a.walking).length,
    [avatars],
  );
  const { now, live } = frame;
  const ref = (id: string) => (el: HTMLDivElement | null) => {
    if (el) labels.set(id, el);
    else labels.delete(id);
  };

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {Object.values(avatars).map((avatar) => {
        const agent = agents[avatar.id];
        const mode = avatarMode(avatar, now);
        const bubble = fast
          ? null
          : replay
            ? avatar.summaryUntil > now
              ? avatar.summary
              : null
            : (live[avatar.id] ?? null);
        const icon = MODE_EMOJI[mode];
        return (
          <div key={avatar.id} ref={ref(avatar.id)} className="absolute top-0 left-0 hidden">
            <div className="flex -translate-x-1/2 -translate-y-full flex-col items-center gap-1">
              {bubble ? (
                <p className="max-w-56 rounded-card border border-line bg-surface px-2 py-1 text-xs shadow-card">
                  {bubbleText(bubble)}
                </p>
              ) : null}
              <span className="flex items-center gap-1 text-base leading-none">
                {avatar.alarmUntil > now ? <span>🚨</span> : null}
                {icon ? <span>{icon}</span> : null}
                {avatar.tool && avatar.toolUntil > now ? (
                  <span>{TOOL_EMOJI[avatar.tool]}</span>
                ) : null}
              </span>
              <span
                className={`rounded-full bg-surface/90 px-2 py-0.5 text-[11px] whitespace-nowrap text-text shadow-card ${
                  selected === avatar.id ? "ring-2 ring-accent" : ""
                }`}
              >
                <strong>{agent?.displayName ?? avatar.id}</strong>{" "}
                <span className="text-muted">
                  {agent ? t(`role.${agent.role}`, { defaultValue: agent.role }) : ""}
                </span>
              </span>
            </div>
          </div>
        );
      })}
      <div ref={ref("break_room")} className="absolute top-0 left-0 hidden">
        <span className="block -translate-x-1/2 rounded-full bg-surface/90 px-2 py-0.5 text-xs shadow-card">
          {t("office.moreResting", { count: Math.max(0, resting - BREAK_ROOM_LIMIT) })}
        </span>
      </div>
    </div>
  );
}
