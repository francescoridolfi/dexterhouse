// SPDX-License-Identifier: AGPL-3.0-or-later
// `/ws/projects/{id}` client (events_ws.md): snapshot on connect, live events, `resync` with
// the last seen event after a reconnect, heartbeat watchdog, exponential backoff.
import type { EventEnvelope, ServerMessage, Snapshot } from "../api/types.ts";
import type { Connection, Speech } from "./model.ts";

export interface SocketHandlers {
  snapshot: (snapshot: Snapshot) => void;
  event: (event: EventEnvelope) => void;
  speak: (speech: Speech) => void;
  connection: (state: Connection) => void;
  lastEventId: () => string | null;
}

type SocketFactory = (url: string) => WebSocket;

const OFFLINE_AFTER_MS = 30_000;
const SILENCE_MS = 60_000;
const FATAL_CODES = new Set([4401, 4403, 4404]);

export class ProjectSocket {
  private ws: WebSocket | null = null;
  private attempts = 0;
  private closed = false;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private watchdog: ReturnType<typeof setTimeout> | null = null;
  private lostAt: number | null = null;
  private hadSnapshot = false;
  private speakingEnabled = true;

  private readonly projectId: string;
  private readonly handlers: SocketHandlers;
  private readonly factory: SocketFactory;
  private readonly location: Pick<Location, "protocol" | "host">;

  constructor(
    projectId: string,
    handlers: SocketHandlers,
    factory: SocketFactory = (url) => new WebSocket(url),
    location: Pick<Location, "protocol" | "host"> = window.location,
  ) {
    this.projectId = projectId;
    this.handlers = handlers;
    this.factory = factory;
    this.location = location;
  }

  url(): string {
    const scheme = this.location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${this.location.host}/ws/projects/${this.projectId}`;
  }

  connect(): void {
    this.closed = false;
    this.handlers.connection(this.attempts === 0 ? "connecting" : "reconnecting");
    const ws = this.factory(this.url());
    this.ws = ws;
    ws.onopen = () => {
      this.attempts = 0;
      this.lostAt = null;
      this.arm();
    };
    ws.onmessage = (message: MessageEvent<string>) => {
      this.arm();
      this.receive(message.data);
    };
    ws.onclose = (event: CloseEvent) => {
      this.disarm();
      if (this.closed) return;
      if (FATAL_CODES.has(event.code)) {
        this.handlers.connection("offline");
        return;
      }
      this.scheduleReconnect();
    };
  }

  close(): void {
    this.closed = true;
    this.disarm();
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.ws?.close(1000);
    this.ws = null;
  }

  /** Toggle the token stream (`agent.speaking`), e.g. "events only" in the live log. */
  setSpeaking(enabled: boolean): void {
    this.speakingEnabled = enabled;
    this.send({ type: "subscribe_speaking", enabled });
  }

  private send(message: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message));
  }

  private receive(raw: string): void {
    let message: ServerMessage;
    try {
      message = JSON.parse(raw) as ServerMessage;
    } catch {
      return;
    }
    switch (message.type) {
      case "snapshot": {
        const since = this.hadSnapshot ? this.handlers.lastEventId() : null;
        this.handlers.snapshot(message);
        this.handlers.connection("live");
        if (since) this.send({ type: "resync", since_event_id: since });
        if (!this.speakingEnabled) this.send({ type: "subscribe_speaking", enabled: false });
        this.hadSnapshot = true;
        break;
      }
      case "event":
        this.handlers.event(message.event);
        break;
      case "speaking":
        this.handlers.speak({
          agentId: message.agent_id,
          turnId: message.turn_id,
          text: message.text,
          seq: message.seq,
        });
        break;
      case "error":
        this.handlers.connection("offline");
        break;
      default:
        break;
    }
  }

  private scheduleReconnect(): void {
    this.lostAt ??= Date.now();
    const offline = Date.now() - this.lostAt >= OFFLINE_AFTER_MS;
    this.handlers.connection(offline ? "offline" : "reconnecting");
    const delay = Math.min(1000 * 2 ** this.attempts, 10_000);
    this.attempts += 1;
    this.retryTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private arm(): void {
    this.disarm();
    this.watchdog = setTimeout(() => {
      this.ws?.close(4000);
    }, SILENCE_MS);
  }

  private disarm(): void {
    if (this.watchdog) clearTimeout(this.watchdog);
    this.watchdog = null;
  }
}
