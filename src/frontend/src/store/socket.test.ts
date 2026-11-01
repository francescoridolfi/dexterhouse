// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EventEnvelope } from "../api/types.ts";
import { event, snapshot } from "../test/fixtures.ts";
import type { Connection } from "./model.ts";
import { ProjectSocket, type SocketHandlers } from "./socket.ts";

class FakeSocket {
  static OPEN = 1;
  readyState = 1;
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  readonly url: string;
  constructor(url: string) {
    this.url = url;
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.onclose?.({ code: 1000 });
  }
  receive(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

function setup() {
  const sockets: FakeSocket[] = [];
  const states: Connection[] = [];
  let last: string | null = null;
  const handlers: SocketHandlers = {
    snapshot: vi.fn(),
    event: vi.fn((e: EventEnvelope) => {
      last = e.id;
    }),
    speak: vi.fn(),
    connection: (s) => states.push(s),
    lastEventId: () => last,
  };
  const socket = new ProjectSocket(
    "p-1",
    handlers,
    (url) => {
      const fake = new FakeSocket(url);
      sockets.push(fake);
      return fake as unknown as WebSocket;
    },
    { protocol: "https:", host: "dh.example" },
  );
  return { socket, sockets, states, handlers };
}

describe("ProjectSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("goes live on the snapshot and forwards events and speech", () => {
    const { socket, sockets, states, handlers } = setup();
    socket.connect();
    const ws = sockets[0]!;
    expect(ws.url).toBe("wss://dh.example/ws/projects/p-1");
    ws.onopen?.();
    ws.receive(snapshot());
    ws.receive({ type: "event", event: event("note.added") });
    ws.receive({ type: "speaking", agent_id: "a", turn_id: "t", text: "hi", seq: 1 });
    ws.receive({ type: "heartbeat", server_time: "now" });
    ws.onmessage?.({ data: "not json" });
    expect(states).toEqual(["connecting", "live"]);
    expect(handlers.event).toHaveBeenCalledTimes(1);
    expect(handlers.speak).toHaveBeenCalledWith({ agentId: "a", turnId: "t", text: "hi", seq: 1 });
    socket.close();
  });

  it("reconnects with backoff and resyncs from the last event", () => {
    const { socket, sockets, states } = setup();
    socket.connect();
    sockets[0]!.receive(snapshot());
    sockets[0]!.receive({ type: "event", event: event("note.added") });
    sockets[0]!.onclose?.({ code: 1006 });
    expect(states.at(-1)).toBe("reconnecting");
    vi.advanceTimersByTime(1000);
    const second = sockets[1]!;
    second.onopen?.();
    second.receive(snapshot());
    expect(second.sent).toContainEqual({
      type: "resync",
      since_event_id: expect.stringMatching(/^e-/) as string,
    });
    socket.setSpeaking(false);
    expect(second.sent).toContainEqual({ type: "subscribe_speaking", enabled: false });
    socket.close();
  });

  it("stops on auth errors and closes silent connections", () => {
    const { socket, sockets, states } = setup();
    socket.connect();
    sockets[0]!.onopen?.();
    vi.advanceTimersByTime(60_000); // watchdog closes the silent socket
    expect(states.at(-1)).toBe("reconnecting");
    vi.advanceTimersByTime(1000);
    sockets[1]!.onclose?.({ code: 4403 });
    expect(states.at(-1)).toBe("offline");
    sockets[1]!.receive({ type: "error", code: "forbidden", detail: "x" });
    socket.close();
  });

  it("reports offline after 30 s of failed reconnects", () => {
    const { socket, sockets, states } = setup();
    socket.connect();
    for (let i = 0; i < 6; i += 1) {
      sockets.at(-1)!.onclose?.({ code: 1006 });
      vi.advanceTimersByTime(10_000);
    }
    expect(states).toContain("offline");
    socket.close();
  });
});
