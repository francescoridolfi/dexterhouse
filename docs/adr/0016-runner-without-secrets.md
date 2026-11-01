# ADR-0016: The runner holds no secrets and writes no events

- Status: accepted · Date: 2026-10-31

## Context
The runner is the service with the Docker socket and runs generated code: it is the most likely target. Pushing to the user's repository requires a token; tracking the runner's actions requires events.

## Decision
The runner has no Fernet key, no DB access and no tokens in its messages. For a push, the core issues a single-use `SecretGrant` (60 s) and the runner redeems it via an authenticated internal endpoint, using the value once through `GIT_ASKPASS`. The runner writes no events: it replies with Celery callbacks on `core-callbacks`, and the core, the only writer of `Event`, persists and publishes them (decisions CD-020, CD-021).

## Alternatives considered
- Token in the Celery payload: travels through Redis in clear text and stays in broker logs.
- Runner with the Fernet key and DB access: compromising the runner compromises everything.
- Runner publishing events directly to Redis: two writers, duplicated outbox, schema validated in two places.

## Consequences
+ A compromised runner exposes at most one workspace and one token for 60 seconds.
+ A single point of validation and ordering for events.
− One extra internal HTTP call for every `deliver`; one extra hop for every runner event (latency under 50 ms).
