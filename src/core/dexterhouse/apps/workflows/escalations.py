# SPDX-License-Identifier: AGPL-3.0-or-later
"""Human escalations (F-004, ADR-0011): one service for every cause, never decided by the system.

The engine escalates by itself when a loop is exhausted (`task_exhausted`), after two rounds
of comments (`rounds_exhausted`), after three failed `exit` checks (`exit_failed`) and after
three failed attempts of a turn (`turn_failed`). Other apps call `escalate`: the tool gateway
for a `risk: high` tool (`tool_high_risk`), the budget check at 100 % (`budget_exceeded`,
E-10). The escalation gate blocks the phase and the project until a human decides:

- `retry`: grant and go on (budget raised, tool allowed for the phase, step run again);
- `accept`: go on without granting (a failed step is skipped, a task is accepted as is);
- `drop`: the phase fails (the project can be retried later).
"""

import uuid
from typing import Any

from django.db import transaction

from dexterhouse.apps.projects.models import Project
from dexterhouse.apps.workflows.engine import common
from dexterhouse.apps.workflows.engine.common import GatePayload
from dexterhouse.apps.workflows.models import (
    ACTIVE_STEP_STATUSES,
    Gate,
    GateDecision,
    GateStatus,
    GateType,
    PhaseRun,
    PhaseStatus,
    ProcessRunStatus,
    StepRun,
)
from dexterhouse.common.errors import InvalidTransitionError

#: Causes `escalate` accepts; the engine's own causes are handled in `engine/gates.py`.
REASONS: dict[str, str] = {
    "budget_exceeded": "The project budget is exhausted",
    "tool_high_risk": "An agent asked for a high-risk tool",
    "turn_failed": "A turn failed three times",
    "security": "An agent turn was blocked for security violations",
}
#: Reasons whose waiting state is not `gate` (state_machines/project.md).
WAITING_REASONS = {"budget_exceeded": "budget"}
_LIVE_PHASES = (PhaseStatus.RUNNING, PhaseStatus.WAITING_GATE, PhaseStatus.REOPENED)


def escalate(
    project: Project | uuid.UUID, reason: str, payload: dict[str, Any] | None = None
) -> Gate:
    """Open a human escalation gate on the project's current phase and return it.

    Idempotent per reason: while an escalation with the same `reason` is open it is returned
    as is (the budget check may call this on every LLM call). `payload` is free JSON shown
    to the human (`Gate.payload.details`); `summary` and `title` in it override the defaults.

    Raises:
        ValueError: unknown `reason` (see `REASONS`).
        InvalidTransitionError: the project has no running process to escalate.
    """
    if reason not in REASONS:
        raise ValueError(f"unknown escalation reason {reason!r}")
    project_id = project.pk if isinstance(project, Project) else project
    with transaction.atomic():
        _project, run = common.lock(project_id)
        open_ = Gate.objects.filter(
            project_id=project_id,
            type=GateType.ESCALATION,
            status=GateStatus.OPEN,
            payload__reason=reason,
        ).first()
        if open_ is not None:
            return open_
        if run is None or run.status not in (
            ProcessRunStatus.RUNNING,
            ProcessRunStatus.WAITING_GATE,
        ):
            raise InvalidTransitionError("the project has no running process to escalate")
        step_run = (
            StepRun.objects.filter(project_id=project_id, status__in=ACTIVE_STEP_STATUSES)
            .select_related("task")
            .first()
        )
        row = step_run.phase_run if step_run else _current_phase(run)
        row.process_run = run
        return open_escalation(row, reason, payload or {}, step_run=step_run)


def _current_phase(run) -> PhaseRun:
    rows = [r for r in common.phase_runs(run) if r.status in _LIVE_PHASES]
    if not rows:
        raise InvalidTransitionError("no phase is running")
    return rows[0]


def open_escalation(
    row: PhaseRun, reason: str, details: dict[str, Any], *, step_run: StepRun | None = None
) -> Gate:
    """Open the gate (the caller holds the engine lock)."""
    task = step_run.task if step_run else None
    title = details.get("title") or f"{REASONS[reason]} ({row.phase_id})"
    summary = details.get("summary") or REASONS[reason]
    if task is not None:
        summary = f"{task.external_id} {task.title}: {summary}"
    payload = GatePayload(
        title=str(title)[:200],
        summary=str(summary)[:400],
        reason=reason,
        step_index=step_run.step_index if step_run and task is None else None,
        round=row.round,
        details=details,
    )
    return common.open_gate(
        row, gate_id="escalation", type=GateType.ESCALATION, payload=payload, task=task
    )


def resolve(phase, row: PhaseRun, gate: Gate, decision: str, comment: str | None) -> str:
    """Effects of a human decision on an escalation opened through `REASONS`; returns `next`."""
    from dexterhouse.apps.workflows.engine import loop

    reason = gate.payload.get("reason")
    step_index = gate.payload.get("step_index")
    if comment:
        ctx = common.get_context(row)
        ctx.comment = comment
        common.set_context(row, ctx)
    if decision == GateDecision.ACCEPT and reason == "turn_failed":
        if gate.task_id is not None:
            task = gate.task
            task.project = row.process_run.project
            loop.complete_task(task, forced=True)
            common.resume_phase(row)
            return "task_accepted"
        if step_index is not None:
            row.current_step = step_index + 1
            common.save(row, "current_step")
    if decision == GateDecision.RETRY and reason == "tool_high_risk" and step_index is not None:
        row.current_step = step_index  # run the step again, now with the tool allowed
        common.save(row, "current_step")
    common.resume_phase(row)
    return "phase_resumed"


def tool_approved(phase_run_id: uuid.UUID | None, tool: str) -> bool:
    """A human allowed `tool` (`retry` on its `tool_high_risk` escalation) in this phase run."""
    if phase_run_id is None:
        return False
    return Gate.objects.filter(
        phase_run_id=phase_run_id,
        type=GateType.ESCALATION,
        decision=GateDecision.RETRY,
        payload__reason="tool_high_risk",
        payload__details__tool=tool,
    ).exists()
