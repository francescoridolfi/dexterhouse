# SPDX-License-Identifier: AGPL-3.0-or-later
"""The team of a project: agent packages by role or name, hiring, the agent of a role.

Packages are the enabled agent PackageVersions the project's organization sees (built-in
first, then installed ones, `apps.packages`); a hired agent is pinned to its version
(`AgentInstance.installed_version`) until the project ends. The built-in team is hired
when the process starts, one agent per role with a stable id; a role without a package
gets a *placeholder* agent (no package, no tools) so the workflow engine always has an
`AgentInstance` to point at. A placeholder can run turns only with the `FakeTurnRunner`.
"""

import uuid
from collections.abc import Iterable, Mapping
from typing import Any

import structlog
from django.db import transaction

from dexterhouse.apps.agents.models import AgentInstance, AgentSource, AgentStatus
from dexterhouse.apps.agents.services.packages import AgentPackage, installed_agent_packages
from dexterhouse.apps.agents.services.turns import create_agent_instance, emit_hired
from dexterhouse.apps.projects.models import Project

logger = structlog.get_logger(__name__)

#: Same namespace as the E-02 placeholder ids, so ids already in events stay valid.
TEAM_NAMESPACE = uuid.UUID("5f0c8a52-4c1e-4d7e-9b2a-6d8e0f3a7c10")
PLACEHOLDER_VERSION = "0.0.0"


def installed_packages(organization_id: uuid.UUID | None = None) -> list[AgentPackage]:
    """Every valid enabled agent package, in lookup order; invalid ones are logged and skipped."""
    return installed_agent_packages(organization_id)


def installed_package_roles(organization_id: uuid.UUID | None = None) -> frozenset[str]:
    return frozenset(p.agent.role for p in installed_packages(organization_id))


def find_package(
    *,
    role: str | None = None,
    name: str | None = None,
    organization_id: uuid.UUID | None = None,
) -> AgentPackage | None:
    """The first valid package with this `name` (or, without a name, for this `role`)."""
    for package in installed_packages(organization_id):
        if package.name == name if name else package.agent.role == role:
            return package
    return None


def team_agent_id(project_id: uuid.UUID, role: str) -> uuid.UUID:
    """Stable id of the built-in team member of `role` in a project."""
    return uuid.uuid5(TEAM_NAMESPACE, f"{project_id}:{role}")


def active_agent(project_id: uuid.UUID, role: str) -> AgentInstance | None:
    agents = AgentInstance.objects.filter(project_id=project_id, role=role)
    return agents.exclude(status=AgentStatus.RELEASED).order_by("hired_at").first()


def ensure_agent(project: Project, role: str, *, room: str | None = None) -> AgentInstance:
    """The project's active agent for `role`, hired on first use (package or placeholder)."""
    agent = active_agent(project.id, role)
    if agent is not None:
        return agent
    agent_id = team_agent_id(project.id, role)
    existing = AgentInstance.objects.filter(pk=agent_id).first()
    if existing is not None:  # released team member: a new one with a fresh id
        agent_id = uuid.uuid4()
    package = find_package(role=role, organization_id=project.organization_id)
    if package is None:
        return hire_placeholder(project, role, agent_id=agent_id, room=room)
    return create_agent_instance(
        organization_id=project.organization_id,
        project_id=project.id,
        package_path=str(package.root),
        source=package.source,
        room=room if not package.agent.office.room else None,
        package_version_id=package.version_id,
        agent_id=agent_id,
    )


def hire_team(project: Project, roles: Iterable[str], rooms: Mapping[str, str]) -> list[Any]:
    """Hire one agent per role (idempotent): the team sits in the break room at start."""
    return [ensure_agent(project, role, room=rooms.get(role)) for role in dict.fromkeys(roles)]


def hire_placeholder(
    project: Project, role: str, *, agent_id: uuid.UUID, room: str | None = None
) -> AgentInstance:
    """An agent without package: visible in the office, runnable only by `FakeTurnRunner`."""
    logger.warning("agents.placeholder_hired", project_id=str(project.id), role=role)
    with transaction.atomic():
        instance = AgentInstance.objects.create(
            id=agent_id,
            organization_id=project.organization_id,
            project=project,
            package_name=f"placeholder-{role.replace('_', '-')}"[:120],
            package_version=PLACEHOLDER_VERSION,
            package_path="",
            role=role,
            display_name=role.replace("_", " ").title()[:80],
            model_profile="balanced",
            allowed_tools=[],
            room=room or "",
            avatar={"model": "default", "color": "#888888"},
            source=AgentSource.BUILTIN,
        )
        emit_hired(instance)
    return instance


def hire_proposed(project: Project, proposals: list[dict[str, Any]]) -> list[AgentInstance]:
    """System action `hire`: one agent per accepted `team_proposal` entry (idempotent).

    The package must be installed (`install_proposed_packages` runs first); its tools are
    granted as listed in the proposal, so `allowed_tools` = package ∩ proposal permissions.
    """
    hired: list[AgentInstance] = []
    for proposal in proposals:
        current = AgentInstance.objects.filter(
            project=project, package_name=proposal["name"], role=proposal["role"]
        ).exclude(status=AgentStatus.RELEASED)
        if (agent := current.first()) is not None:
            hired.append(agent)
            continue
        package = find_package(name=proposal["name"], organization_id=project.organization_id)
        if package is None or package.agent.role != proposal["role"]:
            logger.warning(
                "agents.hire_package_missing",
                project_id=str(project.id),
                package=proposal["name"],
                role=proposal["role"],
            )
            continue
        if package.version != proposal.get("version"):
            logger.info(
                "agents.hire_version_differs",
                package=package.name,
                proposed=proposal.get("version"),
                installed=package.version,
            )
        granted = [p["id"] for p in proposal.get("permissions", [])]
        hired.append(
            create_agent_instance(
                organization_id=project.organization_id,
                project_id=project.id,
                package_path=str(package.root),
                granted_tools=granted,
                source=package.source,
                package_version_id=package.version_id,
            )
        )
    return hired
