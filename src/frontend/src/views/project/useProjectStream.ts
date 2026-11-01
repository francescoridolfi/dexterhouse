// SPDX-License-Identifier: AGPL-3.0-or-later
// Opens the project: REST snapshot for the first paint, then the WebSocket keeps the store
// live (snapshot + events + resync). One connection per project per client.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../../api/endpoints.ts";
import { ProjectSocket } from "../../store/socket.ts";
import { useProjectStore } from "../../store/projectStore.ts";

const INVALIDATING =
  /^(task\.|gate\.|phase\.completed|agent\.(hired|released|turn\.completed)|note\.)/;

export function useProjectStream(projectId: string) {
  const socket = useRef<ProjectSocket | null>(null);
  const [failure, setFailure] = useState<{ projectId: string; error: unknown } | null>(null);
  const client = useQueryClient();

  useEffect(() => {
    const store = useProjectStore.getState();
    store.reset(projectId);
    let alive = true;
    api
      .snapshot(projectId)
      .then((snapshot) => {
        if (alive && !useProjectStore.getState().snapshotLoaded) store.snapshot(snapshot);
      })
      .catch((reason: unknown) => {
        if (alive) setFailure({ projectId, error: reason });
      });
    // The last events for the live log (newest page, cursor pagination is oldest first).
    api
      .recentEvents(projectId)
      .then((page) => {
        if (alive) useProjectStore.getState().history(page.results);
      })
      .catch(() => undefined);
    const ws = new ProjectSocket(projectId, {
      snapshot: (snapshot) => useProjectStore.getState().snapshot(snapshot),
      event: (event) => {
        useProjectStore.getState().event(event);
        if (INVALIDATING.test(event.type)) {
          // REST views of the same project (costs, team, artifacts) refresh in the background.
          void client.invalidateQueries({ queryKey: ["project", projectId] });
          if (event.type.startsWith("gate."))
            void client.invalidateQueries({ queryKey: ["gates"] });
        }
      },
      speak: (speech) => useProjectStore.getState().speak(speech),
      connection: (state) => useProjectStore.getState().setConnection(state),
      lastEventId: () => useProjectStore.getState().lastEventId,
    });
    socket.current = ws;
    ws.connect();
    return () => {
      alive = false;
      ws.close();
      socket.current = null;
    };
  }, [projectId, client]);

  return { socket, error: failure?.projectId === projectId ? failure.error : null };
}
