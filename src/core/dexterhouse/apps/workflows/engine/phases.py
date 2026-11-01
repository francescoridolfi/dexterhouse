# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase scheduling and lifecycle (state_machines/phase_run.md, process_run.md)."""

from typing import Any

from django.utils import timezone

from dexterhouse.apps.projects.models import Artifact, ExecutionMode
from dexterhouse.apps.projects.services.actors import agent_actor, emit
from dexterhouse.apps.projects.services.artifacts import save_artifact
from dexterhouse.apps.workflows import actions
from dexterhouse.apps.workflows.engine import common, loop
from dexterhouse.apps.workflows.engine.common import GatePayload, save
from dexterhouse.apps.workflows.models import (
    GateStatus,
    GateType,
    PhaseRun,
    PhaseStage,
    PhaseStatus,
    ProcessRun,
    ProcessRunStatus,
    StepRun,
    StepRunStatus,
)
from dexterhouse_schema import TurnOutput
from dexterhouse_schema.process import Phase

DONE = (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED)
MAX_PASSES = 200


def advance(run: ProcessRun) -> None:
    """Move every phase as far as the DB state allows; idempotent."""
    for _ in range(MAX_PASSES):
        if run.status not in (ProcessRunStatus.RUNNING, ProcessRunStatus.WAITING_GATE):
            return
        rows = common.phase_runs(run)
        by_id = {row.phase_id: row for row in rows}
        process = common.process_of(run)
        changed = False
        for phase in process.phases:
            row = by_id[phase.id]
            if run.status not in (ProcessRunStatus.RUNNING, ProcessRunStatus.WAITING_GATE):
                return
            changed |= _step_phase(run, phase, row, [by_id[n] for n in phase.needs])
        if all(row.status in DONE for row in rows):
            common.complete_process(run)
            return
        if not changed:
            return
    raise RuntimeError(f"process run {run.id} did not settle")  # pragma: no cover


def _step_phase(run: ProcessRun, phase: Phase, row: PhaseRun, needs: list[PhaseRun]) -> bool:
    needs_done = all(n.status in DONE for n in needs)
    if row.status == PhaseStatus.PENDING and needs_done:
        row.status = PhaseStatus.READY
        row.needs_satisfied_at = timezone.now()
        save(row, "status", "needs_satisfied_at")
        emit(run.project, "phase.ready", {"phase_id": row.phase_id})
        return True
    if row.status == PhaseStatus.READY:
        start_phase(phase, row)
        return True
    if row.status == PhaseStatus.REOPENED and needs_done:
        row.status = PhaseStatus.RUNNING
        save(row, "status")
        return True
    if row.status == PhaseStatus.RUNNING and not common.has_active_step(row):
        if actions.workspace_pending(run.project):
            return False  # resumed by the runner's `ready` callback (workspaces.services)
        return progress(phase, row)
    return False


def start_phase(phase: Phase, row: PhaseRun) -> None:
    project = row.process_run.project
    row.status = PhaseStatus.RUNNING
    row.started_at = timezone.now()
    save(row, "status", "started_at")
    roles = list(dict.fromkeys(s.agent for s in phase.step_list()))
    emit(
        project,
        "phase.started",
        {
            "phase_id": phase.id,
            "room": row.room,
            "agents": [common.agent_for(project, r).id for r in roles],
            "workspace_required": phase.workspace,
        },
    )
    if phase.workspace:
        result = actions.workspace_create(project, row)
        if not result.ok:
            common.fail_phase(row, "workspace", result.detail or "")
            return
    if phase.type == "loop" and not loop.init_tasks(phase, row):
        common.fail_phase(row, "missing_input", f"no {phase.over} artifact to iterate over")


def _after_gate_steps(phase: Phase, row: PhaseRun) -> list[Any]:
    hired = bool(common.get_context(row).hired)
    return [
        s for s in phase.after_gate if s.when in (None, "always") or (s.when == "hired" and hired)
    ]


def progress(phase: Phase, row: PhaseRun) -> bool:
    """Queue the next turn of a running phase, or close its steps."""
    if row.stage == PhaseStage.AFTER_GATE:
        steps = _after_gate_steps(phase, row)
        if row.current_step < len(steps):
            common.queue_step(row, step=steps[row.current_step], step_index=row.current_step)
            return True
        common.complete_phase(row)
        return True
    if phase.type == "loop":
        state = loop.progress(phase, row)
        if state != "done":
            return state == "queued"
        return finish_steps(phase, row)
    steps = phase.step_list()
    if row.current_step < len(steps):
        common.queue_step(row, step=steps[row.current_step], step_index=row.current_step)
        return True
    return finish_steps(phase, row)


def check_exit(row: PhaseRun, phase: Phase, exit_kind: str | None, command: str | None) -> bool:
    """Verify an `exit` condition (core side) and emit `phase.exit_checked`."""
    if exit_kind in (None, "none"):
        return True
    project = row.process_run.project
    detail = None
    if exit_kind == "artifacts_present":
        kinds = set(phase.produces) | {k for s in phase.step_list() for k in s.produces}
        present = set(
            Artifact.objects.filter(phase_run=row, kind__in=kinds).values_list("kind", flat=True)
        )
        missing = sorted(kinds - present)
        ok = not missing
        detail = f"missing: {', '.join(missing)}" if missing else None
    else:
        result = actions.check_exit(project, exit_kind, command)
        ok, detail = result.ok, result.detail
    row.exit_attempts += 1
    save(row, "exit_attempts")
    emit(
        project,
        "phase.exit_checked",
        {
            "phase_id": row.phase_id,
            "exit": exit_kind,
            "ok": ok,
            "attempt": row.exit_attempts,
            "detail": detail,
        },
    )
    if ok:
        row.exit_attempts = 0
        save(row, "exit_attempts")
    return ok


def exit_failed(row: PhaseRun, step_index: int | None) -> None:
    """After a failed exit check: retry the step, or escalate after 3 attempts."""
    if row.exit_attempts < common.MAX_EXIT_ATTEMPTS:
        if step_index is None:
            row.current_step = max(row.current_step - 1, 0)
            save(row, "current_step")
        return
    payload = GatePayload(
        title=f"Exit condition of {row.phase_id} failed",
        summary=f"The exit check failed {row.exit_attempts} times.",
        reason="exit_failed",
        step_index=step_index,
        round=row.round,
    )
    common.open_gate(row, gate_id="escalation", type=GateType.ESCALATION, payload=payload)


def finish_steps(phase: Phase, row: PhaseRun) -> bool:
    """All steps done: phase `exit`, then the gate (or completion)."""
    ctx = common.get_context(row)
    if not ctx.exit_accepted and not check_exit(row, phase, phase.exit, phase.command):
        exit_failed(row, None)
        return True
    gate = phase.gate
    if gate is None:
        common.complete_phase(row)
        return True
    project = row.process_run.project
    artifacts = [
        {
            "id": a.id,
            "kind": a.kind,
            "version": a.version,
            "name": a.name,
            "produced_by_turn": a.produced_by_turn_id,
            "produced_by_role": a.produced_by_role,
        }
        for a in Artifact.objects.filter(phase_run=row).order_by("created_at")
    ]
    payload = GatePayload(
        title=f"Approve {phase.id}",
        summary=f"{len(artifacts)} artifact(s) produced in round {row.round}.",
        artifacts=artifacts,
        on_approve=list(gate.on_approve),
        round=row.round,
        produced_by=_last_turn(row),
    )
    always = project.gate_overrides.get(gate.id) == "always_required"
    supervised = project.execution_mode == ExecutionMode.SUPERVISED
    blocking = always or (supervised and gate.default == "required")
    opened = common.open_gate(
        row, gate_id=gate.id, type=GateType.APPROVAL, payload=payload, block=blocking
    )
    if not blocking:
        common.decide(opened, GateStatus.AUTO_APPROVED, "approve")
        common.gate_decided_event(opened, "phase_completed")
        approve(phase, row)
    return True


def _last_turn(row: PhaseRun) -> dict[str, Any] | None:
    """The turn that closed the phase's steps: who produced what the gate shows."""
    last = (
        StepRun.objects.filter(phase_run=row, status=StepRunStatus.COMPLETED)
        .order_by("-seq")
        .first()
    )
    if last is None:
        return None
    return {
        "step_run_id": last.id,
        "turn_id": last.agent_turn_id,
        "agent_id": last.agent_id,
        "role": last.role,
        "step": last.step,
    }


def approve(phase: Phase, row: PhaseRun) -> None:
    """Approval effects: `on_approve` system actions, then `after_gate` steps or completion."""
    project = row.process_run.project
    ctx = common.get_context(row)
    for name in phase.gate.on_approve if phase.gate else []:
        result = actions.PHASE_ACTIONS[name](project, row)
        if name == "hire":
            ctx.hired = list(result.data.get("hired", []))
    ctx.exit_accepted = False
    common.set_context(row, ctx)
    if _after_gate_steps(phase, row):
        row.status = PhaseStatus.RUNNING
        row.stage = PhaseStage.AFTER_GATE
        row.current_step = 0
        save(row, "status", "stage", "current_step")
        return
    common.complete_phase(row)


def reopen(row: PhaseRun, comment: str | None, *, count_round: bool = True) -> None:
    """Back to the first step with the comment in context (`phase.reopened`)."""
    if count_round:
        row.reopen_count += 1
    row.round += 1
    row.status = PhaseStatus.REOPENED
    row.stage = PhaseStage.STEPS
    row.current_step = 0
    row.exit_attempts = 0
    save(row, "reopen_count", "round", "status", "stage", "current_step", "exit_attempts")
    ctx = common.get_context(row)
    ctx.comment = comment
    ctx.exit_accepted = False
    common.set_context(row, ctx)
    emit(
        row.process_run.project,
        "phase.reopened",
        {"phase_id": row.phase_id, "round": row.round, "comment": comment or ""},
    )


def apply_step(
    phase: Phase,
    row: PhaseRun,
    step_index: int,
    output: TurnOutput,
    step_run: StepRun | None = None,
) -> None:
    """A non-loop step finished: questions, step `exit`, or move to the next step."""
    if output.status == "waiting_answers":
        _questions(phase, row, output, step_run)
        return
    steps = _after_gate_steps(phase, row) if row.stage == PhaseStage.AFTER_GATE else None
    step = (steps or phase.step_list())[step_index]
    if step.exit and not check_exit(row, phase, step.exit, step.command):
        exit_failed(row, step_index)
        return
    row.current_step = step_index + 1
    save(row, "current_step")


def _questions(
    phase: Phase, row: PhaseRun, output: TurnOutput, step_run: StepRun | None = None
) -> None:
    questions = next(
        (
            a.data.model_dump(mode="json")["questions"]
            for a in output.artifacts
            if a.kind == "questions"
        ),
        [],
    )
    ctx = common.get_context(row)
    project = row.process_run.project
    asked = row.gates.filter(type=GateType.QUESTION, payload__round=row.round).count()
    if project.execution_mode == ExecutionMode.AUTONOMOUS or asked >= common.MAX_QUESTION_GATES:
        # Question gates never open in autonomous mode: proceed on the default assumptions.
        ctx.answers = [
            common.Answer(question_id=q["id"], answer=q["default_assumption"]) for q in questions
        ]
        common.set_context(row, ctx)
        if not any(a.kind == "assumptions" for a in output.artifacts):
            _assumptions(row, questions, step_run)
        return
    payload = GatePayload(
        title=f"{len(questions)} question(s) from the {phase.step_list()[0].agent}",
        summary="; ".join(q["text"] for q in questions)[:400],
        questions=questions,
        round=row.round,
    )
    role = phase.step_list()[row.current_step].agent
    agent_id = step_run.agent_id if step_run else common.agent_for(project, role).id
    actor = agent_actor(agent_id, role)
    gate = common.open_gate(
        row, gate_id="question", type=GateType.QUESTION, payload=payload, actor=actor
    )
    emit(
        project,
        "agent.question.asked",
        {
            "turn_id": (step_run.agent_turn_id or step_run.id) if step_run else gate.id,
            "gate_id": gate.id,
            "questions": [
                {k: q[k] for k in ("id", "text", "kind", "options") if q.get(k) is not None}
                for q in questions
            ],
        },
        actor=actor,
        correlation_id=gate.id,
    )


def _assumptions(row: PhaseRun, questions: list[dict[str, Any]], step_run) -> None:
    """Autonomous mode: the unanswered questions become the `assumptions` artifact (F-004)."""
    if not questions:
        return
    data = {
        "assumptions": [
            {
                "id": f"a{i}",
                "question": q["text"],
                "assumed": q["default_assumption"],
                "rationale": q.get("why") or "Default assumption of the agent.",
                "risk": "medium",
            }
            for i, q in enumerate(questions, start=1)
        ]
    }
    lines = [f"- **{a['question']}** {a['assumed']}" for a in data["assumptions"]]
    save_artifact(
        row.process_run.project,
        kind="assumptions",
        name="assumptions.md",
        content="# Assumptions\n\n" + "\n".join(lines) + "\n",
        data=data,
        phase_run_id=row.id,
        turn_id=step_run.agent_turn_id if step_run else None,
        role=step_run.role if step_run else "",
    )
