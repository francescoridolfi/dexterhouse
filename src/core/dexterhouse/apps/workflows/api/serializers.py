# SPDX-License-Identifier: AGPL-3.0-or-later
"""JSON views of the workflow entities (REST v1 and the WebSocket snapshot)."""

from typing import Any

from rest_framework import serializers

from dexterhouse.apps.workflows.models import (
    Estimate,
    Gate,
    GateDecision,
    PhaseRun,
    StepRun,
    Task,
)


def _ts(value: Any) -> str | None:
    return value.isoformat() if value else None


def step_json(step: StepRun) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "seq": step.seq,
        "stage": step.stage,
        "step": step.step,
        "role": step.role,
        "agent_id": str(step.agent_id),
        "task": str(step.task_id) if step.task_id else None,
        "round": step.round,
        "iteration": step.iteration,
        "status": step.status,
        "attempts": step.attempts,
        "summary": (step.output or {}).get("summary"),
        "verdict": (step.output or {}).get("verdict"),
        "error": step.error,
        "started_at": _ts(step.started_at),
        "finished_at": _ts(step.finished_at),
    }


def gate_json(gate: Gate) -> dict[str, Any]:
    return {
        "id": str(gate.id),
        "project": str(gate.project_id),
        "phase_run": str(gate.phase_run_id),
        "task": str(gate.task_id) if gate.task_id else None,
        "gate_id": gate.gate_id,
        "type": gate.type,
        "status": gate.status,
        "payload": gate.payload,
        "decision": gate.decision,
        "comment": gate.comment,
        "answers": gate.answers,
        "decided_by": (
            {"id": str(gate.decided_by_id), "name": gate.decided_by.get_username()}
            if gate.decided_by_id
            else None
        ),
        "opened_at": _ts(gate.opened_at),
        "decided_at": _ts(gate.decided_at),
        "expires_at": _ts(gate.expires_at),
        "title": gate.payload.get("title"),
        "summary": gate.payload.get("summary"),
        "reason": gate.payload.get("reason"),
        "phase_id": gate.phase_run.phase_id,
        "project_name": gate.project.name,
        "reminders": gate.reminders,
        "notified_at": _ts(gate.notified_at),
    }


def phase_json(phase: PhaseRun, open_gate: Gate | None = None) -> dict[str, Any]:
    agents = sorted(set(phase.step_runs.values_list("role", "agent_id"))) if phase.pk else []
    return {
        "id": str(phase.id),
        "phase_id": phase.phase_id,
        "status": phase.status,
        "stage": phase.stage,
        "current_step": phase.current_step,
        "round": phase.round,
        "reopen_count": phase.reopen_count,
        "exit_attempts": phase.exit_attempts,
        "room": phase.room,
        "agents": [{"role": role, "agent_id": str(agent_id)} for role, agent_id in agents],
        "gate": gate_json(open_gate) if open_gate else None,
        "error_code": phase.error_code,
        "started_at": _ts(phase.started_at),
        "finished_at": _ts(phase.finished_at),
    }


def task_json(task: Task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "phase_run": str(task.phase_run_id),
        "external_id": task.external_id,
        "kind": task.kind,
        "parent": str(task.parent_id) if task.parent_id else None,
        "iteration": task.iteration,
        "max_iterations": task.max_iterations,
        "title": task.title,
        "description": task.description,
        "acceptance": task.acceptance,
        "depends_on": [str(d) for d in task.depends_on],
        "estimate": task.estimate,
        "assigned_role": task.assigned_role,
        "assigned_agent": str(task.assigned_instance_id) if task.assigned_instance_id else None,
        "status": task.status,
        "branch": task.branch,
        "order": task.order,
        "current_step": task.current_step,
        "result": task.result,
        "created_at": _ts(task.created_at),
    }


class DecideInput(serializers.Serializer):
    decision = serializers.ChoiceField(choices=GateDecision.values, required=False)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=10_000)
    answers = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField(max_length=5_000)),
        required=False,
    )


class TaskInput(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    acceptance = serializers.ListField(child=serializers.CharField(max_length=1_000), min_length=1)
    assigned_role = serializers.RegexField(r"^[a-z][a-z0-9_]{0,63}$", default="developer")
    depends_on = serializers.ListField(child=serializers.UUIDField(), default=list)
    estimate = serializers.ChoiceField(choices=Estimate.values, default=Estimate.M)
