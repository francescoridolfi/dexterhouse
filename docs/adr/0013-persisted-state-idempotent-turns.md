# ADR-0013: Agent state in Postgres, idempotent turns

- Status: accepted · Date: 2026-10-31

## Context
A project runs for hours; workers and containers restart; LLM calls cost money. Losing an agent's state halfway means redoing the work and paying for it twice.

## Decision
No state in process memory. `AgentTurn` persists messages, tool calls (with idempotency key and result) and output as they happen. The Celery task `run_turn(agent_turn_id)` is idempotent: on retry it resumes from the last saved message and does not re-execute tool calls already recorded. The workflow engine advances only on DB state.

## Alternatives considered
- State in the Celery task / in Redis: lost on restart or hard to inspect.
- Agent frameworks with their own memory (LangGraph checkpointer): adds a state model parallel to our domain.

## Consequences
+ Crash-safe, debuggable from the Django admin, replay possible.
+ Basis for "pause/resume" and for human intervention mid-turn.
− More DB writes per turn (acceptable: a few dozen per turn).
− Non-idempotent tools (e.g. `git.push`) need explicit guards (check remote state before retrying).
