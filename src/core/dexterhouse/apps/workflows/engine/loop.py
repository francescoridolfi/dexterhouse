# SPDX-License-Identifier: AGPL-3.0-or-later
"""`type: loop` phases: one task at a time in topological order (task.md, CD-038)."""

import re
from typing import Any, Literal

from django.db.models import Max
from django.utils import timezone

from dexterhouse.apps.observability.services import costs
from dexterhouse.apps.projects.models import Artifact, Project
from dexterhouse.apps.projects.services.actors import SYSTEM, agent_actor, emit
from dexterhouse.apps.workflows import actions
from dexterhouse.apps.workflows.engine import common
from dexterhouse.apps.workflows.engine.common import GatePayload, save
from dexterhouse.apps.workflows.models import (
    ACTIVE_TASK_STATUSES,
    GateType,
    PhaseRun,
    StepRun,
    StepRunStatus,
    Task,
    TaskKind,
    TaskStatus,
)
from dexterhouse_schema import TurnOutput
from dexterhouse_schema.artifacts.task_board import TaskBoard
from dexterhouse_schema.process import Phase

STEP_STATUS = [TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW, TaskStatus.IN_TEST]
NEGATIVE = frozenset({"request_changes", "fail"})
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)


def _status_for(index: int) -> str:
    return STEP_STATUS[min(index, len(STEP_STATUS) - 1)]


def top_level(row: PhaseRun) -> list[Task]:
    return list(Task.objects.filter(phase_run=row, parent__isnull=True).order_by("order"))


def task_created_event(task: Task, actor: Any = SYSTEM) -> None:
    emit(
        task.project,
        "task.created",
        {
            "task_id": task.id,
            "external_id": task.external_id,
            "kind": task.kind,
            "parent_id": task.parent_id,
            "iteration": task.iteration,
            "title": task.title,
            "assigned_role": task.assigned_role,
            "depends_on": task.depends_on,
            "estimate": task.estimate,
        },
        actor=actor,
        correlation_id=task.parent_id or task.id,
    )


def init_tasks(phase: Phase, row: PhaseRun) -> bool:
    """Create the tasks of the loop from the latest `over` artifact (once per phase run)."""
    if Task.objects.filter(phase_run=row).exists():
        return True
    project = row.process_run.project
    board = (
        Artifact.objects.filter(project=project, kind=phase.over).order_by("-created_at").first()
    )
    if board is None or not board.data:
        return False
    parsed = TaskBoard.model_validate(board.data)
    order = {tid: i for i, tid in enumerate(parsed.topological_order())}
    created: dict[str, Task] = {}
    for item in sorted(parsed.tasks, key=lambda t: order[t.external_id]):
        task = Task.objects.create(
            project=project,
            phase_run=row,
            external_id=item.external_id,
            title=item.title,
            description=item.description,
            acceptance=list(item.acceptance),
            depends_on=[created[d].id for d in item.depends_on],
            estimate=item.estimate,
            assigned_role=item.assigned_role,
            max_iterations=phase.max_iterations or 1,
            order=order[item.external_id],
        )
        created[item.external_id] = task
        task_created_event(task)
    return True


def next_external_id(project: Project) -> str:
    numbers = [
        int(m.group(1))
        for e in Task.objects.filter(project=project).values_list("external_id", flat=True)
        if (m := re.fullmatch(r"T-(\d+)", e))
    ]
    return f"T-{max(numbers, default=0) + 1:02d}"


def add_task(row: PhaseRun, phase: Phase, *, actor: Any = SYSTEM, **fields: Any) -> Task:
    """Append a top-level task to the board (user feature or release fix)."""
    project = row.process_run.project
    last = Task.objects.filter(phase_run=row).aggregate(m=Max("order"))["m"]
    task = Task.objects.create(
        project=project,
        phase_run=row,
        external_id=next_external_id(project),
        max_iterations=phase.max_iterations or 1,
        order=(last if last is not None else -1) + 1,
        **fields,
    )
    task_created_event(task, actor)
    return task


def fix_tasks_from_comment(row: PhaseRun, phase: Phase, comment: str) -> list[Task]:
    """CD-034: one `fix` task per numbered paragraph of the comment (one if not numbered)."""
    parts = [p.strip() for p in _NUMBERED.split(comment or "") if p.strip()]
    parts = parts if len(_NUMBERED.findall(comment or "")) > 1 else [comment.strip() or "Fix"]
    return [
        add_task(
            row,
            phase,
            kind=TaskKind.FIX,
            title=part.splitlines()[0][:200],
            description=part,
            acceptance=[part[:500]],
            assigned_role="developer",
            estimate="S",
        )
        for part in parts
    ]


def progress(phase: Phase, row: PhaseRun) -> Literal["queued", "blocked", "done"]:
    tasks = top_level(row)
    active = next((t for t in tasks if t.status in ACTIVE_TASK_STATUSES), None)
    if active is not None:
        _queue(phase, row, active)
        return "queued"
    done = {t.id for t in tasks if t.status == TaskStatus.DONE}
    for task in tasks:
        if task.status == TaskStatus.PENDING and set(task.depends_on) <= done:
            task.status = TaskStatus.READY
            task.assigned_instance = common.agent_for(task.project, task.assigned_role)
            save(task, "status", "assigned_instance")
            emit(task.project, "task.ready", {"task_id": task.id})
    ready = [t for t in tasks if t.status == TaskStatus.READY]
    if ready:
        _start(phase, row, ready[0])
        return "queued"
    if any(t.status in (TaskStatus.PENDING, TaskStatus.ESCALATED) for t in tasks):
        return "blocked"
    return "done"


def _start(phase: Phase, row: PhaseRun, task: Task) -> None:
    first = phase.step_list()[0]
    task.status = TaskStatus.IN_PROGRESS
    task.current_step = first.agent
    task.started_at = task.started_at or timezone.now()
    new_branch = task.branch is None
    task.branch = task.branch or f"task/{task.external_id}"
    save(task, "status", "current_step", "started_at", "branch")
    if new_branch:
        actions.branch_create(task.project, task)
    emit(
        task.project,
        "task.started",
        {
            "task_id": task.id,
            "agent_id": task.assigned_instance_id
            or common.agent_for(task.project, task.assigned_role).id,
            "branch": task.branch,
            "iteration": task.iteration,
        },
        correlation_id=task.id,
    )
    _queue(phase, row, task)


def _queue(phase: Phase, row: PhaseRun, task: Task) -> None:
    steps = phase.step_list()
    index = next(i for i, s in enumerate(steps) if s.agent == task.current_step)
    role = task.assigned_role if index == 0 else steps[index].agent
    common.queue_step(row, step=steps[index], step_index=index, role=role, task=task)


def apply_step(phase: Phase, row: PhaseRun, step_run: StepRun, output: TurnOutput, refs) -> None:
    """A loop step finished: next step, new iteration, escalation or completion."""
    task = Task.objects.get(pk=step_run.task_id)
    task.project = row.process_run.project
    steps = phase.step_list()
    step = steps[step_run.step_index]
    emit(
        task.project,
        "task.step.completed",
        {
            "task_id": task.id,
            "step": step.agent,
            "agent_id": step_run.agent_id,
            "verdict": output.verdict,
            "artifact": refs[0],
        },
        actor=agent_actor(step_run.agent_id, step_run.role),
        correlation_id=task.id,
    )
    if output.verdict is not None:
        review = next((a.data for a in output.artifacts if a.kind == "review"), None)
        task.result = {
            "step": step.agent,
            "verdict": output.verdict,
            "blocking_count": review.blocking_count if review else 0,
            "contested": False,
            "findings_open": [f.id for f in review.findings if not f.resolved] if review else [],
        }
        save(task, "result")
    if output.verdict in NEGATIVE:
        reason = "review" if output.verdict == "request_changes" else "tests"
        iterate(phase, row, task, reason, findings=task.result.get("blocking_count"))
        return
    if step_run.step_index + 1 < len(steps):
        task.current_step = steps[step_run.step_index + 1].agent
        task.status = _status_for(step_run.step_index + 1)
        save(task, "current_step", "status")
        return
    complete_task(task, forced=False)


def iterate(
    phase: Phase, row: PhaseRun, task: Task, reason: str, findings: int | None = None
) -> None:
    if task.iteration >= task.max_iterations:
        if phase.on_exhausted == "fail":
            common.fail_phase(row, "loop_exhausted", f"{task.external_id} exhausted iterations")
        else:
            escalate(row, task)
        return
    _close_children(task, TaskStatus.DONE)
    task.iteration += 1
    task.status = TaskStatus.IN_PROGRESS
    task.current_step = phase.step_list()[0].agent
    save(task, "iteration", "status", "current_step")
    fix = Task.objects.create(
        project=task.project,
        phase_run=row,
        external_id=task.external_id,
        kind=TaskKind.FIX,
        parent=task,
        iteration=task.iteration,
        max_iterations=task.max_iterations,
        title=f"Fix {reason} findings of {task.external_id} (iteration {task.iteration})"[:200],
        description=(task.result or {}).get("verdict", ""),
        acceptance=task.acceptance,
        estimate=task.estimate,
        assigned_role=task.assigned_role,
        assigned_instance=task.assigned_instance,
        status=TaskStatus.IN_PROGRESS,
        branch=task.branch,
        order=task.order,
        current_step=task.current_step,
    )
    task_created_event(fix)
    emit(
        task.project,
        "task.iteration",
        {
            "task_id": task.id,
            "iteration": task.iteration,
            "max_iterations": task.max_iterations,
            "reason": reason,
            "fix_task_id": fix.id,
            "findings_count": findings,
        },
        correlation_id=task.id,
    )


def _attempts(task: Task) -> list[dict[str, Any]]:
    rows = StepRun.objects.filter(task=task, status=StepRunStatus.COMPLETED).order_by("seq")
    return [
        {
            "iteration": r.iteration,
            "step": r.step,
            "verdict": r.output["verdict"],
            "summary": r.output["summary"],
        }
        for r in rows
        if r.output and r.output.get("verdict")
    ]


def escalate(row: PhaseRun, task: Task) -> None:
    task.status = TaskStatus.ESCALATED
    save(task, "status")
    _close_children(task, TaskStatus.ESCALATED)
    attempts = _attempts(task)
    payload = GatePayload(
        title=f"{task.external_id} exhausted {task.max_iterations} iterations",
        summary=f"{task.title}: {len(attempts)} verdict(s) so far.",
        attempts=attempts,
        reason="task_exhausted",
        round=row.round,
    )
    gate = common.open_gate(
        row, gate_id="escalation", type=GateType.ESCALATION, payload=payload, task=task
    )
    emit(
        task.project,
        "task.escalated",
        {"task_id": task.id, "gate_id": gate.id, "attempts": attempts},
        correlation_id=task.id,
    )


def complete_task(task: Task, *, forced: bool) -> None:
    commit = actions.merge(task.project, task).data["commit"]
    task.status = TaskStatus.DONE
    task.current_step = None
    task.finished_at = timezone.now()
    save(task, "status", "current_step", "finished_at")
    _close_children(task, TaskStatus.DONE)
    emit(
        task.project,
        "task.completed",
        {
            "task_id": task.id,
            "iterations": task.iteration,
            "duration_s": common.duration(task.started_at),
            "cost": costs.task_cost(task.id),
            "merged_commit": commit,
            "forced": forced,
        },
        correlation_id=task.id,
    )


def cancel_task(task: Task, reason: str, actor: Any = SYSTEM) -> None:
    """Cancel a task, its fix children and (transitively) the tasks that depend on it."""
    task.status = TaskStatus.CANCELLED
    task.current_step = None
    save(task, "status", "current_step")
    _close_children(task, TaskStatus.CANCELLED)
    emit(task.project, "task.cancelled", {"task_id": task.id, "reason": reason}, actor=actor)
    dependents = Task.objects.filter(
        project=task.project,
        depends_on__contains=[task.id],
        status__in=[TaskStatus.PENDING, TaskStatus.READY],
    )
    for dependent in dependents:
        dependent.project = task.project
        cancel_task(dependent, "dependency_cancelled")


def retry_task(phase: Phase, row: PhaseRun, task: Task) -> None:
    """Escalation `retry`: one more iteration (max_iterations + 1)."""
    task.max_iterations += 1
    save(task, "max_iterations")
    iterate(phase, row, task, "human")


def _close_children(task: Task, status: str) -> None:
    Task.objects.filter(parent=task).exclude(
        status__in=[TaskStatus.DONE, TaskStatus.CANCELLED]
    ).update(status=status, updated_at=timezone.now())
