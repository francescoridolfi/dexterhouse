# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared engine helpers: definitions, step queueing, gates, waiting and terminal states."""

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field

from dexterhouse.apps.agents.models import AgentInstance
from dexterhouse.apps.agents.services.roster import ensure_agent
from dexterhouse.apps.projects.models import Project, ProjectStatus
from dexterhouse.apps.projects.services.actors import SYSTEM, emit
from dexterhouse.apps.projects.services.transitions import transition
from dexterhouse.apps.workflows.models import (
    ACTIVE_STEP_STATUSES,
    Gate,
    GateStatus,
    PhaseRun,
    PhaseStatus,
    ProcessRun,
    ProcessRunStatus,
    StepRun,
    StepRunStatus,
    Task,
    TaskStatus,
)
from dexterhouse.apps.workflows.roles import role_room
from dexterhouse_schema import Process
from dexterhouse_schema.process import Phase, Step

MAX_EXIT_ATTEMPTS = 3
MAX_REOPEN_ROUNDS = 2
MAX_QUESTION_GATES = 2


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    answer: str


class PhaseContext(BaseModel):
    """`PhaseRun.context`: what the next turns of the phase must see."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = None
    answers: list[Answer] = Field(default_factory=list)
    hired: list[str] = Field(default_factory=list)
    exit_accepted: bool = False


class GatePayload(BaseModel):
    """`Gate.payload`, immutable after opening."""

    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    on_approve: list[str] = Field(default_factory=list)
    reason: str | None = None
    step_index: int | None = None
    round: int = 0
    produced_by: dict[str, Any] | None = None  # the turn that produced the artifacts
    details: dict[str, Any] = Field(default_factory=dict)  # escalation data (escalations.py)


def process_of(run: ProcessRun) -> Process:
    return Process.model_validate(run.definition)


def phase_of(run: ProcessRun, phase_run: PhaseRun) -> Phase:
    return next(p for p in process_of(run).phases if p.id == phase_run.phase_id)


def get_context(phase_run: PhaseRun) -> PhaseContext:
    return PhaseContext.model_validate(phase_run.context or {})


def set_context(phase_run: PhaseRun, ctx: PhaseContext) -> None:
    phase_run.context = ctx.model_dump(mode="json")
    phase_run.save(update_fields=["context", "updated_at"])


def save(obj: Any, *fields: str) -> None:
    obj.save(update_fields=[*fields, "updated_at"])


def agent_for(project: Project, role: str) -> AgentInstance:
    """The project's agent for `role` (hired on first use)."""
    return ensure_agent(project, role, room=role_room(role))


def has_active_step(phase_run: PhaseRun) -> bool:
    return StepRun.objects.filter(phase_run=phase_run, status__in=ACTIVE_STEP_STATUSES).exists()


def queue_step(
    phase_run: PhaseRun,
    *,
    step: Step,
    step_index: int,
    role: str | None = None,
    task: Task | None = None,
) -> StepRun:
    """Create the next StepRun of the phase (unique per phase while active) and dispatch it."""
    project = phase_run.process_run.project
    role = role or step.agent
    seq = (StepRun.objects.filter(phase_run=phase_run).aggregate(m=Max("seq"))["m"] or 0) + 1
    step_run = StepRun.objects.create(
        project=project,
        phase_run=phase_run,
        task=task,
        seq=seq,
        stage=phase_run.stage,
        step_index=step_index,
        step=step.step or step.agent,
        role=role,
        agent=_task_agent(task, role) or agent_for(project, role),
        round=phase_run.round,
        iteration=task.iteration if task else 1,
    )
    dispatch(step_run)
    return step_run


def _task_agent(task: Task | None, role: str) -> AgentInstance | None:
    """A task's own steps go to its assigned agent (resolved when the task got ready)."""
    if task is None or task.assigned_instance_id is None:
        return None
    agent = task.assigned_instance
    return agent if agent.role == role and agent.status != "released" else None


def dispatch(step_run: StepRun) -> None:
    """Send `run_step` after commit; the worker refuses it while the project is not running."""
    from dexterhouse.apps.workflows import tasks

    step_id = str(step_run.id)
    transaction.on_commit(lambda: tasks.run_step.delay(step_id))


def dispatch_pending(project: Project) -> int:
    """Re-dispatch queued steps and running ones whose lease expired (resume, reconcile)."""
    now = timezone.now()
    pending = StepRun.objects.filter(project=project, status=StepRunStatus.QUEUED) | (
        StepRun.objects.filter(
            project=project, status=StepRunStatus.RUNNING, lease_expires_at__lt=now
        )
    )
    count = 0
    for step_run in pending:
        dispatch(step_run)
        count += 1
    return count


def open_gate(
    phase_run: PhaseRun,
    *,
    gate_id: str,
    type: str,
    payload: GatePayload,
    task: Task | None = None,
    actor: Any = SYSTEM,
    block: bool = True,
) -> Gate:
    """Create a gate and emit `gate.opened`; a blocking gate puts the phase in waiting_gate."""
    project = phase_run.process_run.project
    ttl = gate_ttl(project) if block else None
    gate = Gate.objects.create(
        project=project,
        phase_run=phase_run,
        task=task,
        gate_id=gate_id,
        type=type,
        payload=payload.model_dump(mode="json"),
        expires_at=timezone.now() + ttl if ttl else None,
        notified_at=timezone.now() if block else None,
    )
    emit(
        project,
        "gate.opened",
        {
            "gate_id": gate.id,
            "type": type,
            "phase_id": phase_run.phase_id,
            "task_id": task.id if task else None,
            "title": payload.title,
            "summary": payload.summary,
            "artifacts": [
                {"id": a["id"], "kind": a["kind"], "version": a["version"]}
                for a in payload.artifacts
            ],
            "expires_at": gate.expires_at,
        },
        actor=actor,
        correlation_id=gate.id,
    )
    if block:
        notify_gate(gate)
        phase_run.status = PhaseStatus.WAITING_GATE
        save(phase_run, "status")
        sync_waiting(phase_run.process_run)
    return gate


def gate_ttl(project: Project) -> timedelta | None:
    """`OrganizationSettings.gate_ttl_hours` (default: no TTL): when reminders are sent."""
    hours = (project.organization.settings or {}).get("gate_ttl_hours")
    return timedelta(hours=float(hours)) if hours else None


def notify_gate(gate: Gate, *, reminder: int = 0) -> None:
    from dexterhouse.apps.notifications.services import notify_gate as notify

    notify(gate, reminder=reminder)


def resume_phase(phase_run: PhaseRun) -> None:
    """Back to `running` once the phase has no open gate left."""
    if (
        phase_run.status == PhaseStatus.WAITING_GATE
        and not phase_run.gates.filter(status=GateStatus.OPEN).exists()
    ):
        phase_run.status = PhaseStatus.RUNNING
        save(phase_run, "status")


def _waiting_reason(gate: Gate) -> str:
    from dexterhouse.apps.workflows.escalations import WAITING_REASONS

    return WAITING_REASONS.get(gate.payload.get("reason") or "", "gate")


def sync_waiting(run: ProcessRun) -> None:
    """Couple ProcessRun/Project waiting states to the open gates of the project."""
    project = run.project
    gate = Gate.objects.filter(project=project, status=GateStatus.OPEN).order_by("-opened_at")
    gate = gate.first()
    if gate is not None:
        if run.status == ProcessRunStatus.RUNNING:
            run.status = ProcessRunStatus.WAITING_GATE
            save(run, "status")
        if project.status == ProjectStatus.RUNNING:
            reason = _waiting_reason(gate)
            transition(project, ProjectStatus.WAITING, waiting_reason=reason)
            emit(project, "project.waiting", {"reason": reason, "gate_id": gate.id})
        return
    if run.status == ProcessRunStatus.WAITING_GATE:
        run.status = ProcessRunStatus.RUNNING
        save(run, "status")
    if project.status == ProjectStatus.WAITING and project.waiting_reason in ("gate", "budget"):
        reason = project.waiting_reason
        transition(project, ProjectStatus.RUNNING)
        emit(project, "project.resumed", {"reason": reason})
        dispatch_pending(project)


def decide(gate: Gate, status: str, decision: str | None, *, user: Any = None, **fields: Any):
    """Record a decision on an open gate (callers check that it is open)."""
    gate.status = status
    gate.decision = decision
    gate.decided_by = user
    gate.decided_at = timezone.now()
    for name, value in fields.items():
        setattr(gate, name, value)
    save(gate, "status", "decision", "decided_by", "decided_at", *fields)
    from dexterhouse.apps.notifications.services import gate_closed

    gate_closed(gate)
    if (gate.comment or "").strip():
        index_comment(gate)


def index_comment(gate: Gate) -> None:
    """Gate comments enter the project memory with the higher weight (F-013, CD-034)."""
    from dexterhouse.apps.memory.tasks import index_comment_task

    args = (str(gate.project.organization_id), str(gate.project_id), str(gate.id), gate.comment)
    transaction.on_commit(lambda: index_comment_task.delay(*args, kind="gate_comment"))


def gate_decided_event(gate: Gate, next_: str, *, actor: Any = SYSTEM) -> None:
    by = (
        {"id": gate.decided_by.id, "name": gate.decided_by.get_username()}
        if gate.decided_by
        else None
    )
    emit(
        gate.project,
        "gate.decided",
        {
            "gate_id": gate.id,
            "type": gate.type,
            "decision": gate.decision,
            "comment": gate.comment,
            "decided_by": by,
            "auto": gate.status == GateStatus.AUTO_APPROVED,
            "next": next_,
        },
        actor=actor,
        correlation_id=gate.id,
    )


def duration(start: Any) -> float:
    return round((timezone.now() - start).total_seconds(), 3) if start else 0.0


def complete_phase(phase_run: PhaseRun) -> None:
    phase_run.status = PhaseStatus.COMPLETED
    phase_run.finished_at = timezone.now()
    save(phase_run, "status", "finished_at")
    emit(
        phase_run.process_run.project,
        "phase.completed",
        {"phase_id": phase_run.phase_id, "duration_s": duration(phase_run.started_at), "cost": 0},
    )


def fail_phase(phase_run: PhaseRun, error_code: str, detail: str = "") -> None:
    """Fail the phase, the process and the project (no escalation left)."""
    run = phase_run.process_run
    phase_run.status = PhaseStatus.FAILED
    phase_run.error_code = error_code
    phase_run.finished_at = timezone.now()
    save(phase_run, "status", "error_code", "finished_at")
    emit(run.project, "phase.failed", {"phase_id": phase_run.phase_id, "error_code": error_code})
    run.status = ProcessRunStatus.FAILED
    run.error_code = error_code
    run.error_detail = detail or None
    run.finished_at = timezone.now()
    save(run, "status", "error_code", "error_detail", "finished_at")
    emit(run.project, "process.failed", {"error_code": error_code})
    project = run.project
    if project.status != ProjectStatus.FAILED:
        transition(project, ProjectStatus.FAILED)
        emit(project, "project.failed", {"error_code": error_code, "phase_id": phase_run.phase_id})


def complete_process(run: ProcessRun) -> None:
    run.status = ProcessRunStatus.COMPLETED
    run.finished_at = timezone.now()
    save(run, "status", "finished_at")
    emit(run.project, "process.completed", {"error_code": None})
    project = run.project
    top = Task.objects.filter(project=project, parent__isnull=True)
    transition(project, ProjectStatus.COMPLETED)
    emit(
        project,
        "project.completed",
        {
            "duration_s": duration(project.started_at),
            "cost": project.spent,
            "tasks_done": top.filter(status=TaskStatus.DONE).count(),
            "iterations_total": sum(t.iteration for t in top),
        },
    )


def cancel_process(run: ProcessRun) -> None:
    """Project archived: revoke queued turns and close open gates' processing."""
    if run.status in (ProcessRunStatus.COMPLETED, ProcessRunStatus.FAILED):
        return
    run.status = ProcessRunStatus.CANCELLED
    run.finished_at = timezone.now()
    save(run, "status", "finished_at")
    StepRun.objects.filter(phase_run__process_run=run, status__in=ACTIVE_STEP_STATUSES).update(
        status=StepRunStatus.CANCELLED, finished_at=timezone.now()
    )
    emit(run.project, "process.cancelled", {"error_code": None})


def lock(project_id: Any) -> tuple[Project, ProcessRun | None]:
    """Lock the project, then its process run (the engine's single lock order)."""
    project = Project.objects.select_for_update().get(pk=project_id)
    run = ProcessRun.objects.select_for_update().filter(project=project).first()
    if run is not None:
        run.project = project
    return project, run


def phase_runs(run: ProcessRun) -> list[PhaseRun]:
    """Phase runs in definition order, sharing the locked `run` instance."""
    rows = list(PhaseRun.objects.filter(process_run=run).order_by("position"))
    for row in rows:
        row.process_run = run
    return rows
