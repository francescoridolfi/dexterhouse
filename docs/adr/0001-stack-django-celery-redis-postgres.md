# ADR-0001: Stack: Django, Celery, Redis, PostgreSQL in Docker Compose

- Status: accepted · Date: 2026-10-31

## Context
We need a mature backend with ORM, admin, auth, async tasks and WebSockets, installable with one command. This was an explicit constraint from the project owner.

## Decision
Python 3.12, Django 5 + DRF + Channels, Celery 5 with Redis 7 as broker and result backend, PostgreSQL 16 with pgvector, all orchestrated by Docker Compose.

## Alternatives considered
- FastAPI + SQLAlchemy: lighter, but no admin and more infrastructure code to write.
- Temporal/Prefect for workflows: powerful, but one more service and a steep learning curve; our engine is simple (a state machine).
- RabbitMQ as broker: more robust for huge queues, but Redis is already needed for Channels and Streams.

## Consequences
+ One backend language, a huge ecosystem, a free admin for debugging.
+ Redis reused for three purposes (broker, Streams, Channels layer).
− Celery is not ideal for long-running workflows: state must live in the DB, never in the task (see [ADR-0013](0013-persisted-state-idempotent-turns.md)).
− Channels in production requires uvicorn/daphne and care when scaling.
