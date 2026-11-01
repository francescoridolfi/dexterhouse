# SPDX-License-Identifier: AGPL-3.0-or-later
"""Full project state for a new client (`snapshot` over WebSocket and REST)."""

from typing import Any

from dexterhouse.apps.agents.models import AgentInstance, AgentStatus
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.api.serializers import project_json
from dexterhouse.apps.projects.models import Project
from dexterhouse.apps.workflows.api.serializers import gate_json, phase_json, task_json
from dexterhouse.apps.workflows.models import (
    ACTIVE_STEP_STATUSES,
    Gate,
    GateStatus,
    PhaseRun,
    StepRun,
    Task,
)
from dexterhouse.apps.workflows.roles import role_room

IDLE_ROOM = "break_room"


def _agents(project: Project) -> list[dict[str, Any]]:
    """The hired agents: working in the room of their active step, else idle."""
    active = {
        s.agent_id: s.phase_run.room or role_room(s.role)
        for s in StepRun.objects.filter(
            project=project, status__in=ACTIVE_STEP_STATUSES
        ).select_related("phase_run")
    }
    agents = AgentInstance.objects.filter(project=project).exclude(status=AgentStatus.RELEASED)
    return [
        {
            "agent_id": str(agent.id),
            "role": agent.role,
            "display_name": agent.display_name,
            "room": active.get(agent.id, IDLE_ROOM),
            "status": "working" if agent.id in active else "idle",
            "avatar": agent.avatar,
        }
        for agent in agents.order_by("role", "hired_at")
    ]


def build_snapshot(project: Project) -> dict[str, Any]:
    open_gates = list(
        Gate.objects.filter(project=project, status=GateStatus.OPEN).select_related("decided_by")
    )
    by_phase = {g.phase_run_id: g for g in open_gates}
    phases = PhaseRun.objects.filter(process_run__project=project).select_related("process_run")
    last = Event.objects.filter(project_id=project.id).order_by("-created_at", "-id").first()
    return {
        "type": "snapshot",
        "project": project_json(project, detail=True),
        "phases": [phase_json(p, by_phase.get(p.id)) for p in phases.order_by("position")],
        "tasks": [task_json(t) for t in Task.objects.filter(project=project).order_by("order")],
        "gates_open": [gate_json(g) for g in open_gates],
        "agents": _agents(project),
        "workspace": None,
        "budget": {"budget": str(project.budget), "spent": str(project.spent)},
        "last_event_id": str(last.id) if last else None,
    }
