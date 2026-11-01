# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run one StepRun: claim it, call the TurnRunner outside any transaction, apply once.

Crash safety (ADR-0013): the claim and the application are two short transactions. A worker
killed during the turn leaves the row `running` with a lease; `reconcile` re-dispatches it
when the lease expires and the next claim bumps `attempts`. The application checks that the
row is still claimed by the same attempt, so a late or duplicate worker never applies twice.
"""

import uuid
from datetime import timedelta

import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pydantic import ValidationError

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.projects.models import Artifact, Note, ProjectStatus
from dexterhouse.apps.projects.services import notes as notes_service
from dexterhouse.apps.projects.services.actors import emit
from dexterhouse.apps.projects.services.artifacts import ref, save_artifact
from dexterhouse.apps.workflows import escalations
from dexterhouse.apps.workflows.engine import common, loop, phases
from dexterhouse.apps.workflows.models import (
    PhaseRun,
    PhaseStage,
    ProcessRunStatus,
    StepRun,
    StepRunStatus,
    Task,
)
from dexterhouse.apps.workflows.runner import (
    TaskBrief,
    TurnFailedError,
    TurnRequest,
    get_runner,
    verdict_rule,
)
from dexterhouse_schema import TurnOutput, validate_turn_output

logger = structlog.get_logger(__name__)
RECONCILE_QUEUED_AFTER = timedelta(seconds=30)


def build_request(step_run: StepRun, attempt: int) -> TurnRequest:
    row = step_run.phase_run
    run = row.process_run
    project = run.project
    phase = common.phase_of(run, row)
    steps = phases._after_gate_steps(phase, row) if step_run.stage == "after_gate" else None
    step = (steps or phase.step_list())[step_run.step_index]
    ctx = common.get_context(row)
    task = step_run.task
    notes = Note.objects.filter(project=project).filter(phase_run__isnull=True) | (
        Note.objects.filter(project=project, phase_run=row)
    )
    produces = list(step.produces) or (list(phase.produces) if phase.agent else [])
    return TurnRequest(
        step_run_id=step_run.id,
        attempt=attempt,
        organization_id=project.organization_id,
        project_id=project.id,
        process=run.process_name,
        phase_id=row.phase_id,
        step=step_run.step,
        role=step_run.role,
        agent_id=step_run.agent_id,
        execution_mode=project.execution_mode,
        may_ask=phase.may_ask and step_run.stage == PhaseStage.STEPS,
        produces=[] if task else produces,
        verdict_rule=verdict_rule(step.agent),
        round=row.round,
        brief=project.brief,
        stack=project.stack,
        task=_task_brief(task) if task else None,
        comment=ctx.comment,
        answers=[a.model_dump() for a in ctx.answers],
        notes=[n.content for n in notes.order_by("created_at")],
    )


def _task_brief(task: Task) -> TaskBrief:
    return TaskBrief(
        id=task.id,
        external_id=task.external_id,
        kind=task.kind,
        title=task.title,
        description=task.description,
        acceptance=list(task.acceptance),
        iteration=task.iteration,
        max_iterations=task.max_iterations,
        branch=task.branch,
        previous_result=task.result,
    )


def claim(step_run_id: uuid.UUID) -> TurnRequest | None:
    """Mark the step running for a new attempt, or None if it must not run now."""
    exhausted = False
    with transaction.atomic():
        step_run = (
            StepRun.objects.select_for_update(of=("self",))
            .select_related("phase_run__process_run__project", "task")
            .filter(pk=step_run_id)
            .first()
        )
        if step_run is None or step_run.status not in common.ACTIVE_STEP_STATUSES:
            return None
        now = timezone.now()
        if step_run.status == StepRunStatus.RUNNING and step_run.lease_expires_at > now:
            return None
        if step_run.project.status != ProjectStatus.RUNNING:
            return None
        exhausted = step_run.attempts >= settings.WORKFLOWS_STEP_MAX_ATTEMPTS
        if not exhausted:
            request = _start_attempt(step_run, now)
    if exhausted:
        record_failure(step_run_id, None, "attempts_exhausted")
        return None
    return request


def _start_attempt(step_run: StepRun, now) -> TurnRequest:
    step_run.attempts += 1
    step_run.status = StepRunStatus.RUNNING
    step_run.lease_expires_at = now + timedelta(seconds=settings.WORKFLOWS_STEP_LEASE_S)
    step_run.started_at = step_run.started_at or now
    request = build_request(step_run, step_run.attempts)
    step_run.request = request.model_dump(mode="json")
    step_run.save(
        update_fields=[
            "attempts",
            "status",
            "lease_expires_at",
            "started_at",
            "request",
            "updated_at",
        ]
    )
    return request


def run_step(step_run_id: uuid.UUID) -> None:
    """Celery entry point (`tasks.run_step`)."""
    request = claim(step_run_id)
    if request is None:
        return
    try:
        output = get_runner().run(request)
        output = validate_turn_output(output.model_dump(mode="json"), request.turn_context())
    except TurnFailedError as exc:
        record_failure(step_run_id, request.attempt, exc.code, str(exc))
        return
    except ValidationError as exc:
        record_failure(step_run_id, request.attempt, "output_contract", str(exc))
        return
    complete(step_run_id, request.attempt, output)


def _locked(step_run_id: uuid.UUID, attempt: int | None):
    """Lock project, run and step; None when another attempt owns the step."""
    project_id = StepRun.objects.filter(pk=step_run_id).values_list("project_id", flat=True)
    project, run = common.lock(project_id.get())
    step_run = StepRun.objects.select_for_update().get(pk=step_run_id)
    if step_run.status not in common.ACTIVE_STEP_STATUSES:
        return None
    if attempt is not None and step_run.attempts != attempt:
        return None
    row = PhaseRun.objects.get(pk=step_run.phase_run_id)
    row.process_run = run
    step_run.phase_run = row
    step_run.project = project
    return run, row, step_run


def complete(step_run_id: uuid.UUID, attempt: int, output: TurnOutput) -> None:
    with transaction.atomic():
        locked = _locked(step_run_id, attempt)
        if locked is None:
            logger.info("workflows.step_stale", step_run_id=str(step_run_id), attempt=attempt)
            return
        run, row, step_run = locked
        now = timezone.now()
        step_run.output = output.model_dump(mode="json")
        step_run.finished_at = now
        step_run.lease_expires_at = None
        if run.status not in (ProcessRunStatus.RUNNING, ProcessRunStatus.WAITING_GATE):
            step_run.status = StepRunStatus.CANCELLED
            step_run.save(update_fields=["output", "finished_at", "lease_expires_at", "status"])
            return
        step_run.status = StepRunStatus.COMPLETED
        step_run.save(
            update_fields=["output", "finished_at", "lease_expires_at", "status", "updated_at"]
        )
        _apply(run, row, step_run, output)
        phases.advance(run)


def _apply(run, row: PhaseRun, step_run: StepRun, output: TurnOutput) -> None:
    project = run.project
    phase = common.phase_of(run, row)
    refs = [ref(a) for a in _artifacts(project, row, step_run, output)]
    _consume_notes(project, row, step_run)
    if step_run.task_id:
        loop.apply_step(phase, row, step_run, output, refs)
        return
    emit(
        project,
        "phase.step.completed",
        {
            "phase_id": row.phase_id,
            "step": step_run.step,
            "agent_id": step_run.agent_id,
            "artifacts": refs,
        },
    )
    phases.apply_step(phase, row, step_run.step_index, output, step_run)


def _consume_notes(project, row: PhaseRun, step_run: StepRun) -> None:
    """The user's notes the turn had in context are read (`note.consumed`, F-004)."""
    if step_run.agent_turn_id is not None:
        manifest = (
            AgentTurn.objects.filter(pk=step_run.agent_turn_id)
            .values_list("context_manifest", flat=True)
            .first()
        )
        sections = (manifest or {}).get("sections") or {}
        ids = [n["note_id"] for n in sections.get("notes") or []]
    else:
        texts = set((step_run.request or {}).get("notes") or [])
        scope = Note.objects.filter(project=project, phase_run__isnull=True) | Note.objects.filter(
            project=project, phase_run=row
        )
        ids = [n.id for n in scope if n.content in texts]
    if ids:
        turn_id = step_run.agent_turn_id or step_run.id
        notes_service.consume(project, ids, turn_id, step_run.agent_id, step_run.role)


def _artifacts(project, row: PhaseRun, step_run: StepRun, output: TurnOutput) -> list[Artifact]:
    """The output's artifacts: stored by the agent turn already, or saved now (fake runner)."""
    if step_run.agent_turn_id is not None:
        stored = Artifact.objects.filter(produced_by_turn_id=step_run.agent_turn_id)
        return list(stored.order_by("created_at", "id"))
    return [
        save_artifact(
            project,
            kind=a.kind,
            name=a.name,
            content=getattr(a, "content", ""),
            data=a.data.model_dump(mode="json") if hasattr(a, "data") else None,
            phase_run_id=row.id,
            role=step_run.role,
        )
        for a in output.artifacts
    ]


def record_failure(step_run_id: uuid.UUID, attempt: int | None, code: str, detail: str = ""):
    """Retry the step later, or fail the phase after `WORKFLOWS_STEP_MAX_ATTEMPTS`."""
    with transaction.atomic():
        locked = _locked(step_run_id, attempt)
        if locked is None:
            return
        _run, row, step_run = locked
        step_run.error = f"{code}: {detail}" if detail else code
        step_run.lease_expires_at = None
        if code == "budget":
            # The project waits for a budget raise (F-012): the attempt does not count and
            # `resume_run` re-dispatches the step.
            step_run.status = StepRunStatus.QUEUED
            step_run.attempts = max(step_run.attempts - 1, 0)
            step_run.save(
                update_fields=["error", "lease_expires_at", "status", "attempts", "updated_at"]
            )
            return
        if step_run.attempts < settings.WORKFLOWS_STEP_MAX_ATTEMPTS:
            step_run.status = StepRunStatus.QUEUED
            step_run.save(update_fields=["error", "lease_expires_at", "status", "updated_at"])
            common.dispatch(step_run)
            return
        step_run.status = StepRunStatus.FAILED
        step_run.finished_at = timezone.now()
        step_run.save(
            update_fields=["error", "lease_expires_at", "status", "finished_at", "updated_at"]
        )
        logger.warning("workflows.step_failed", step_run_id=str(step_run_id), code=code)
        escalations.open_escalation(
            row,
            "turn_failed",
            {"error": step_run.error[:2000], "step": step_run.step, "role": step_run.role},
            step_run=step_run,
        )


def reconcile(now=None) -> int:
    """Beat: re-dispatch queued steps nobody picked up and running ones with expired leases."""
    now = now or timezone.now()
    stale = StepRun.objects.filter(
        project__status=ProjectStatus.RUNNING,
        status=StepRunStatus.QUEUED,
        updated_at__lt=now - RECONCILE_QUEUED_AFTER,
    ) | StepRun.objects.filter(
        project__status=ProjectStatus.RUNNING,
        status=StepRunStatus.RUNNING,
        lease_expires_at__lt=now,
    )
    count = 0
    with transaction.atomic():
        for step_run in stale:
            common.dispatch(step_run)
            count += 1
    if count:
        logger.info("workflows.reconciled", count=count)
    return count
