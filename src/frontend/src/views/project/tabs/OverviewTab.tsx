// SPDX-License-Identifier: AGPL-3.0-or-later
import type { RefObject } from "react";

import type { ProjectSocket } from "../../../store/socket.ts";
import { LiveLog } from "../panels/LiveLog.tsx";
import { NoteComposer } from "../panels/NoteComposer.tsx";
import { Pipeline } from "../panels/Pipeline.tsx";
import { TeamNow } from "../panels/TeamNow.tsx";

export function OverviewTab({
  socket,
  onOpenGate,
}: {
  socket: RefObject<ProjectSocket | null>;
  onOpenGate: (id: string) => void;
}) {
  return (
    <div className="space-y-4">
      <Pipeline onOpenGate={onOpenGate} />
      <div className="grid gap-4 @5xl:grid-cols-[minmax(16rem,1fr)_2fr]">
        <TeamNow />
        <LiveLog socket={socket} />
      </div>
      <NoteComposer />
    </div>
  );
}
