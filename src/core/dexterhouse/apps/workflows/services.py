# SPDX-License-Identifier: AGPL-3.0-or-later
"""User operations on phases, tasks and gates; each takes the engine lock."""

import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.projects.services.actors import emit, user_actor
from dexterhouse.apps.workflows.engine import common, gates, loop, phases
from dexterhouse.apps.workflows.models import (
    Gate,
    GateStatus,
    PhaseRun,
    PhaseStatus,
    Task,
    TaskStatus,
)
from dexterhouse.common.errors import InvalidTransitionError, ValidationFailedError

EDITABLE_TASK_FIELDS = frozenset(
    {"title", "description", "acceptance", "assigned_role", "depends_on"}
)


def decide(gate_id: uuid.UUID, user: User, **body: Any) -> tuple[Gate, str]:
    with transaction.atomic():
        project_id = Gate.objects.values_list("project_id", flat=True).get(pk=gate_id)
        _project, run = common.lock(project_id)
        gate = Gate.objects.select_for_update().get(pk=gate_id)
        next_ = gates.decide_gate(run, gate, user, **body)
    gate.refresh_from_db()
    return gate, next_


def skip_phase(phase_run_id: uuid.UUID, user: User) -> PhaseRun:
    """Admin: a pending phase counts as done for its dependents (`phase.skipped`)."""
    with transaction.atomic():
        project_id = PhaseRun.objects.values_list("process_run__project_id", flat=True).get(
            pk=phase_run_id
        )
        project, run = common.lock(project_id)
        row = PhaseRun.objects.select_for_update().get(pk=phase_run_id)
        if row.status != PhaseStatus.PENDING:
            raise InvalidTransitionError(f"only pending phases can be skipped, not {row.status}")
        row.status = PhaseStatus.SKIPPED
        row.finished_at = timezone.now()
        common.save(row, "status", "finished_at")
        emit(project, "phase.skipped", {"phase_id": row.phase_id}, actor=user_actor(user))
        phases.advance(run)
    return row


def _deps(task: Task | None, row: PhaseRun, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    known = set(
        Task.objects.filter(phase_run=row, parent__isnull=True, pk__in=ids).values_list(
            "pk", flat=True
        )
    )
    unknown = [str(i) for i in ids if i not in known or (task and i == task.pk)]
    if unknown:
        raise ValidationFailedError(
            "unknown dependencies",
            [{"field": "depends_on", "message": f"not tasks of this phase: {', '.join(unknown)}"}],
        )
    return list(ids)


def add_task(project_id: uuid.UUID, user: User, data: dict[str, Any]) -> Task:
    """Member: add a feature task to the board while the loop phase runs."""
    with transaction.atomic():
        _project, run = common.lock(project_id)
        row = None
        if run is not None:
            process = common.process_of(run)
            loop_ids = [p.id for p in process.phases if p.type == "loop"]
            row = PhaseRun.objects.filter(
                process_run=run,
                phase_id__in=loop_ids,
                status__in=[PhaseStatus.RUNNING, PhaseStatus.WAITING_GATE],
            ).first()
        if row is None:
            raise InvalidTransitionError("tasks can be added only while a loop phase runs")
        row.process_run = run
        phase = common.phase_of(run, row)
        data = {**data, "depends_on": _deps(None, row, data.get("depends_on", []))}
        task = loop.add_task(row, phase, actor=user_actor(user), **data)
        phases.advance(run)
    return task


def update_task(task_id: uuid.UUID, user: User, data: dict[str, Any]) -> Task:
    with transaction.atomic():
        task = Task.objects.select_for_update().get(pk=task_id)
        if task.status != TaskStatus.PENDING:
            raise InvalidTransitionError(f"only pending tasks can be edited, not {task.status}")
        bad = sorted(set(data) - EDITABLE_TASK_FIELDS)
        if bad:
            raise ValidationFailedError(
                "read-only fields", [{"field": f, "message": "cannot be edited"} for f in bad]
            )
        if "depends_on" in data:
            data["depends_on"] = _deps(task, task.phase_run, data["depends_on"])
        for name, value in data.items():
            setattr(task, name, value)
        common.save(task, *data)
        changes = {k: [str(i) for i in v] if k == "depends_on" else v for k, v in data.items()}
        emit(
            task.project,
            "task.updated",
            {"task_id": task.id, "changes": changes},
            actor=user_actor(user),
        )
    return task


def cancel_task(task_id: uuid.UUID, user: User) -> Task:
    """Admin: pending/ready tasks are cancelled; an escalated one is dropped via its gate."""
    project_id = Task.objects.values_list("project_id", flat=True).get(pk=task_id)
    task = Task.objects.get(pk=task_id)
    if task.status == TaskStatus.ESCALATED:
        gate = Gate.objects.filter(task=task, status=GateStatus.OPEN).first()
        if gate is not None:
            decide(gate.id, user, decision="drop", comment="cancelled by user")
            return Task.objects.get(pk=task_id)
    with transaction.atomic():
        project, run = common.lock(project_id)
        task = Task.objects.select_for_update().get(pk=task_id)
        if task.status not in (TaskStatus.PENDING, TaskStatus.READY) or task.parent_id:
            raise InvalidTransitionError(f"task cannot be cancelled from {task.status}")
        task.project = project
        loop.cancel_task(task, "cancelled by user", actor=user_actor(user))
        if run is not None:
            phases.advance(run)
    return task
