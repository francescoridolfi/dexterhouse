# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent roles and rooms until the agents app (E-03) provides AgentPackage/AgentInstance."""

import uuid

from dexterhouse_schema import Process
from dexterhouse_schema.process import Phase

BUILTIN_ROLES = frozenset(
    {"analyst", "architect", "project_manager", "recruiter", "developer", "reviewer", "tester"}
)
# Default room of each built-in agent (ux/office_layout.md); packages declare `office.room`.
ROLE_ROOMS = {
    "analyst": "meeting_room",
    "architect": "design_studio",
    "project_manager": "pm_office",
    "recruiter": "hr_office",
    "developer": "open_space",
    "reviewer": "review_corner",
    "tester": "qa_lab",
}
FALLBACK_ROOM = "open_space"
_AGENT_NAMESPACE = uuid.UUID("5f0c8a52-4c1e-4d7e-9b2a-6d8e0f3a7c10")


def installed_roles() -> frozenset[str]:
    """Roles a process may reference; E-03 replaces this with the installed agent packages."""
    return BUILTIN_ROLES


def agent_id_for(project_id: uuid.UUID, role: str) -> uuid.UUID:
    """Stable placeholder agent id per (project, role); becomes AgentInstance.id in E-03."""
    return uuid.uuid5(_AGENT_NAMESPACE, f"{project_id}:{role}")


def phase_room(process: Process, phase: Phase) -> str:
    if phase.id in process.rooms:
        return process.rooms[phase.id]
    steps = phase.step_list()
    return ROLE_ROOMS.get(steps[0].agent, FALLBACK_ROOM) if steps else FALLBACK_ROOM


def process_roles(process: Process) -> set[str]:
    return {s.agent for p in process.phases for s in [*p.step_list(), *p.after_gate]}
