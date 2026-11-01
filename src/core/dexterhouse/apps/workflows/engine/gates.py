# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gate decisions (state_machines/gate.md): approval, question, escalation."""

from typing import Any

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.projects.services.actors import emit, user_actor
from dexterhouse.apps.workflows.engine import common, loop, phases
from dexterhouse.apps.workflows.models import (
    Gate,
    GateDecision,
    GateStatus,
    GateType,
    PhaseRun,
    PhaseStatus,
    ProcessRun,
    ProcessRunStatus,
    Task,
)
from dexterhouse.common.errors import InvalidTransitionError, ValidationFailedError

APPROVAL_DECISIONS = {GateDecision.APPROVE, GateDecision.REJECT, GateDecision.APPROVE_WITH_COMMENTS}
ESCALATION_DECISIONS = {GateDecision.RETRY, GateDecision.ACCEPT, GateDecision.DROP}


def decide_gate(
    run: ProcessRun,
    gate: Gate,
    user: User,
    *,
    decision: str | None = None,
    comment: str | None = None,
    answers: list[dict[str, str]] | None = None,
) -> str:
    """Apply a human decision; returns `next` (what happens). The caller holds the lock."""
    if gate.status != GateStatus.OPEN:
        who = gate.decided_by.get_username() if gate.decided_by else "the system"
        raise InvalidTransitionError(f"Gate already decided by {who} at {gate.decided_at}")
    if run.status not in (ProcessRunStatus.RUNNING, ProcessRunStatus.WAITING_GATE):
        raise InvalidTransitionError(f"the process run is {run.status}")
    row = PhaseRun.objects.get(pk=gate.phase_run_id)
    row.process_run = run
    gate.project = run.project
    phase = common.phase_of(run, row)
    if gate.type == GateType.QUESTION:
        next_ = _answer(row, gate, user, answers)
    elif gate.type == GateType.APPROVAL:
        next_ = _approval(phase, row, gate, user, decision, comment)
    else:
        next_ = _escalation(phase, row, gate, user, decision, comment)
    common.sync_waiting(run)
    phases.advance(run)
    return next_


def _answer(row: PhaseRun, gate: Gate, user: User, answers: Any) -> str:
    expected = [q["id"] for q in gate.payload.get("questions", [])]
    given = {a["question_id"]: a["answer"] for a in answers or []}
    missing = [qid for qid in expected if not str(given.get(qid, "")).strip()]
    if missing:
        raise ValidationFailedError(
            "every question needs an answer",
            [{"field": f"answers.{qid}", "message": "missing answer"} for qid in missing],
        )
    clean = [{"question_id": qid, "answer": given[qid]} for qid in expected]
    common.decide(gate, GateStatus.ANSWERED, None, user=user, answers=clean)
    ctx = common.get_context(row)
    ctx.answers = [common.Answer(**a) for a in clean]
    common.set_context(row, ctx)
    row.status = PhaseStatus.RUNNING
    common.save(row, "status")
    emit(
        gate.project,
        "question.answered",
        {"gate_id": gate.id, "answers": clean},
        actor=user_actor(user),
        correlation_id=gate.id,
    )
    return "phase_resumed"


def _check(decision: str | None, allowed: set[str], kind: str) -> str:
    if decision not in allowed:
        raise ValidationFailedError(
            f"invalid decision for an {kind} gate",
            [{"field": "decision", "message": f"one of {', '.join(sorted(allowed))}"}],
        )
    return decision


def _approval(phase, row: PhaseRun, gate: Gate, user: User, decision, comment) -> str:
    decision = _check(decision, APPROVAL_DECISIONS, "approval")
    actor = user_actor(user)
    if decision == GateDecision.APPROVE:
        common.decide(gate, GateStatus.APPROVED, decision, user=user, comment=comment)
        common.gate_decided_event(gate, "phase_completed", actor=actor)
        phases.approve(phase, row)
        return "phase_completed"
    if decision == GateDecision.APPROVE_WITH_COMMENTS:
        if not (comment or "").strip():
            raise ValidationFailedError(
                "approve_with_comments needs a comment",
                [{"field": "comment", "message": "required"}],
            )
        common.decide(gate, GateStatus.APPROVED_WITH_COMMENTS, decision, user=user, comment=comment)
        if row.reopen_count >= common.MAX_REOPEN_ROUNDS:
            common.gate_decided_event(gate, "escalated", actor=actor)
            payload = common.GatePayload(
                title=f"{row.phase_id}: comments after {row.reopen_count} rounds",
                summary=comment[:400],
                reason="rounds_exhausted",
                round=row.round,
            )
            common.open_gate(row, gate_id="escalation", type=GateType.ESCALATION, payload=payload)
            return "escalated"
        common.gate_decided_event(gate, "phase_reopened", actor=actor)
        phases.reopen(row, comment)
        return "phase_reopened"
    common.decide(gate, GateStatus.REJECTED, decision, user=user, comment=comment)
    if phase.gate and phase.gate.on_reject == "reopen_implementation":
        created = _reopen_loop(phase, row, comment or "")
        if created:
            common.gate_decided_event(gate, "tasks_created", actor=actor)
            return "tasks_created"
    common.gate_decided_event(gate, "phase_failed", actor=actor)
    common.fail_phase(row, "gate_rejected", comment or "")
    return "phase_failed"


def _reopen_loop(phase, row: PhaseRun, comment: str) -> list[Task]:
    """`reject` with `reopen_implementation`: fix tasks in the upstream loop phase."""
    run = row.process_run
    process = common.process_of(run)
    ancestors = process.ancestors(phase.id)
    target = next((p for p in process.phases if p.id in ancestors and p.type == "loop"), None)
    if target is None:
        return []
    loop_row = PhaseRun.objects.get(process_run=run, phase_id=target.id)
    loop_row.process_run = run
    tasks = loop.fix_tasks_from_comment(loop_row, target, comment)
    phases.reopen(loop_row, comment, count_round=False)
    phases.reopen(row, comment, count_round=False)
    return tasks


def _escalation(phase, row: PhaseRun, gate: Gate, user: User, decision, comment) -> str:
    decision = _check(decision, ESCALATION_DECISIONS, "escalation")
    status = GateStatus.REJECTED if decision == GateDecision.DROP else GateStatus.APPROVED
    common.decide(gate, status, decision, user=user, comment=comment)
    actor = user_actor(user)
    reason = gate.payload.get("reason")
    if reason == "task_exhausted":
        task = Task.objects.get(pk=gate.task_id)
        task.project = row.process_run.project
        next_ = {"retry": "task_retried", "accept": "task_accepted", "drop": "task_dropped"}[
            decision
        ]
        common.gate_decided_event(gate, next_, actor=actor)
        row.status = PhaseStatus.RUNNING
        common.save(row, "status")
        if decision == GateDecision.RETRY:
            loop.retry_task(phase, row, task)
        elif decision == GateDecision.ACCEPT:
            loop.complete_task(task, forced=True)
        else:
            loop.cancel_task(task, "dropped by human", actor=actor)
        return next_
    if decision == GateDecision.DROP:
        common.gate_decided_event(gate, "phase_failed", actor=actor)
        common.fail_phase(row, "escalation_dropped", comment or "")
        return "phase_failed"
    if decision == GateDecision.RETRY:
        common.gate_decided_event(gate, "phase_reopened", actor=actor)
        if reason == "exit_failed":
            row.exit_attempts = 0
            row.status = PhaseStatus.RUNNING
            if gate.payload.get("step_index") is None:
                row.current_step = max(row.current_step - 1, 0)
            common.save(row, "exit_attempts", "status", "current_step")
        else:
            phases.reopen(row, comment or gate.comment, count_round=False)
        return "phase_reopened"
    common.gate_decided_event(gate, "phase_completed", actor=actor)
    step_index = gate.payload.get("step_index")
    row.status = PhaseStatus.RUNNING
    row.exit_attempts = 0
    if reason == "exit_failed" and step_index is not None:
        row.current_step = step_index + 1
        common.save(row, "status", "exit_attempts", "current_step")
        return "phase_completed"
    common.save(row, "status", "exit_attempts")
    ctx = common.get_context(row)
    ctx.exit_accepted = True
    common.set_context(row, ctx)
    if reason == "rounds_exhausted":
        phases.approve(phase, row)
    return "phase_completed"
