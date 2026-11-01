# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent roles and rooms of the processes; the agents themselves live in `agents.roster`."""

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


def installed_roles(organization_id: uuid.UUID | None = None) -> frozenset[str]:
    """Roles a process may reference: the built-in team plus the installed agent packages."""
    from dexterhouse.apps.agents.services.roster import installed_package_roles

    return BUILTIN_ROLES | installed_package_roles(organization_id)


def role_room(role: str) -> str:
    return ROLE_ROOMS.get(role, FALLBACK_ROOM)


def phase_room(process: Process, phase: Phase) -> str:
    if phase.id in process.rooms:
        return process.rooms[phase.id]
    steps = phase.step_list()
    return ROLE_ROOMS.get(steps[0].agent, FALLBACK_ROOM) if steps else FALLBACK_ROOM


def process_roles(process: Process) -> set[str]:
    return {s.agent for p in process.phases for s in [*p.step_list(), *p.after_gate]}
