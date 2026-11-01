# ADR-0005: Event bus on Redis Streams with Postgres persistence

- Status: accepted · Date: 2026-10-31

## Context
The 3D office, the dashboard, metrics, webhooks and replay need to see what happens without coupling to the runtime.

## Decision
Every state change produces a typed event (versioned pydantic schema), written first to Postgres (`events`, append-only) and then published to Redis Streams, one stream per project, with a consumer group per consumer type. Channels forwards events to the browser.

## Alternatives considered
- Redis pub/sub: simpler, but loses messages when a consumer is slow or disconnected.
- Kafka/NATS: overkill for a single-host installation.
- Postgres LISTEN/NOTIFY only: limited payload, no consumer groups.

## Consequences
+ Full replay from the `events` table; the 3D view is a pure function of the stream.
+ Independent consumers can be added without touching producers (webhooks, Slack, metrics).
− Double write: needs an outbox (`published` flag + republish job).
− The `events` table grows: monthly partitioning and configurable retention.
