// SPDX-License-Identifier: AGPL-3.0-or-later
import { type RefObject, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Card } from "../../../components/Feedback.tsx";
import { TONE_CLASS, actorLabel, describeEvent } from "../../../utils/events.ts";
import { time } from "../../../utils/format.ts";
import { useProjectStore } from "../../../store/projectStore.ts";
import type { ProjectSocket } from "../../../store/socket.ts";

const LIVE_ROWS = 80;
const QUIET = new Set(["agent.tool.requested", "agent.status", "agent.moved", "agent.turn.queued"]);

/** Newest first; `agent.speaking` shows as one updating line per agent (throttled server-side). */
export function LiveLog({ socket }: { socket: RefObject<ProjectSocket | null> }) {
  const { t } = useTranslation();
  const events = useProjectStore((s) => s.events);
  const agents = useProjectStore((s) => s.agents);
  const tasks = useProjectStore((s) => s.tasks);
  const speaking = useProjectStore((s) => s.speaking);
  const snapshotLoaded = useProjectStore((s) => s.snapshotLoaded);
  const [frozen, setFrozen] = useState<typeof events | null>(null);
  const [stream, setStream] = useState(true);
  const paused = frozen !== null;
  const rows = (frozen ?? events)
    .filter((e) => !QUIET.has(e.type))
    .slice(-LIVE_ROWS)
    .reverse();

  useEffect(() => {
    socket.current?.setSpeaking(stream);
  }, [stream, socket]);

  return (
    <Card
      title={t("log.live")}
      actions={
        <div className="flex gap-2 text-xs">
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={!stream}
              onChange={(e) => setStream(!e.target.checked)}
            />
            {t("log.eventsOnly")}
          </label>
          <button
            type="button"
            className="min-h-8 rounded px-2 hover:bg-bg"
            aria-pressed={paused}
            onClick={() => setFrozen(paused ? null : events)}
          >
            {paused ? t("log.resumeScroll") : t("log.pauseScroll")}
          </button>
        </div>
      }
    >
      <div className="max-h-[28rem] overflow-y-auto font-mono text-xs">
        {stream
          ? Object.values(speaking).map((speech) => (
              <p
                key={speech.agentId}
                className="flex gap-2 border-b border-line bg-bg/60 px-3 py-1.5 italic"
              >
                <span className="shrink-0 text-muted">
                  {agents[speech.agentId]?.displayName ?? "…"}
                </span>
                <span aria-hidden>💬</span>
                <span className="line-clamp-2">“{speech.text}”</span>
              </p>
            ))
          : null}
        <ol aria-live="polite" aria-relevant="additions">
          {rows.length === 0 ? (
            <li className="px-3 py-6 text-center text-muted">
              {snapshotLoaded ? t("log.waiting") : t("loading")}
            </li>
          ) : (
            rows.map((event) => {
              const line = describeEvent(event, t, tasks);
              return (
                <li
                  key={event.id}
                  className="grid grid-cols-[4.5rem_7rem_1.25rem_1fr] gap-1 px-3 py-1 hover:bg-bg"
                >
                  <time dateTime={event.created_at} className="text-muted">
                    {time(event.created_at)}
                  </time>
                  <span className="truncate">{actorLabel(event, agents, t)}</span>
                  <span aria-hidden>{line.icon}</span>
                  <span className={`break-words ${TONE_CLASS[line.tone]}`}>{line.text}</span>
                </li>
              );
            })
          )}
        </ol>
      </div>
    </Card>
  );
}
