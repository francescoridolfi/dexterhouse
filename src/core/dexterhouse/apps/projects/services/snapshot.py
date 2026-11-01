# SPDX-License-Identifier: AGPL-3.0-or-later
"""Full project state for a new client (`snapshot` over WebSocket and REST)."""

from typing import Any

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
from dexterhouse.apps.workflows.roles import ROLE_ROOMS, agent_id_for

IDLE_ROOM = "break_room"


def _agents(project: Project) -> list[dict[str, Any]]:
    """Agents from the process roles: working in the room of their active step, else idle.

    E-03 replaces this with the project's AgentInstances.
    """
    active = {
        s.role: s for s in StepRun.objects.filter(project=project, status__in=ACTIVE_STEP_STATUSES)
    }
    roles = sorted(set(ROLE_ROOMS) | set(active))
    return [
        {
            "agent_id": str(agent_id_for(project.id, role)),
            "role": role,
            "room": ROLE_ROOMS.get(role, "open_space") if role in active else IDLE_ROOM,
            "status": "working" if role in active else "idle",
        }
        for role in roles
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
