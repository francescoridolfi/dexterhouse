# SPDX-License-Identifier: AGPL-3.0-or-later
"""Create and edit projects (F-001)."""

from decimal import Decimal
from typing import Any

from django.utils.text import slugify

from dexterhouse.apps.accounts.models import Organization, User
from dexterhouse.apps.projects.models import ArtifactKind, Project, ProjectStatus
from dexterhouse.apps.projects.services.actors import emit, user_actor
from dexterhouse.apps.projects.services.artifacts import save_artifact, validate_data
from dexterhouse.apps.workflows.registry import get_process
from dexterhouse.common import crypto
from dexterhouse.common.errors import InvalidTransitionError, ValidationFailedError

DEFAULT_PROCESS = "software-house-default"
EDITABLE_WHILE_ACTIVE = frozenset({"name", "budget", "gate_overrides", "delivery_mode"})


def _unique_slug(organization: Organization, name: str) -> str:
    base = (slugify(name) or "project")[:56]
    slug, n = base, 1
    while Project.objects.filter(organization=organization, slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def create_project(organization: Organization, user: User, data: dict[str, Any]) -> Project:
    """Create a `draft` project, its `brief` artifact v1 and `project.created`."""
    process_name = data.get("process") or DEFAULT_PROCESS
    installed = get_process(process_name)
    if installed is None:
        raise ValidationFailedError(
            "unknown process",
            [{"field": "process", "message": f"{process_name} is not installed"}],
        )
    stack = validate_data(ArtifactKind.STACK, data["stack"]) if data.get("stack") else None
    token = data.get("remote_token")
    project = Project.objects.create(
        organization=organization,
        name=data["name"],
        slug=_unique_slug(organization, data["name"]),
        brief=data["brief"],
        execution_mode=data.get("execution_mode", "supervised"),
        gate_overrides=data.get("gate_overrides") or {},
        process_name=installed.name,
        process_version=installed.version,
        model_profile_overrides=data.get("model_profile_overrides"),
        data_residency=data.get("data_residency", "any"),
        budget=data["budget"],
        remote_repo_url=data.get("remote_repo_url") or None,
        remote_token=crypto.encrypt(token) if token else None,
        delivery_mode=data.get("delivery_mode", "pull_request"),
        created_by=user,
    )
    save_artifact(project, kind=ArtifactKind.BRIEF, name="brief.md", content=project.brief)
    if stack:
        save_artifact(project, kind=ArtifactKind.STACK, name="stack.yaml", data=stack)
    emit(
        project,
        "project.created",
        {
            "name": project.name,
            "execution_mode": project.execution_mode,
            "budget": project.budget,
            "process": {"name": installed.name, "version": installed.version},
        },
        actor=user_actor(user),
    )
    # Memory indexing of the brief (F-013) belongs to the memory app (E-03).
    return project


def update_project(project: Project, user: User, data: dict[str, Any]) -> Project:
    """PATCH: every field in `draft`; afterwards only name, budget, gate overrides, delivery."""
    if project.status == ProjectStatus.ARCHIVED:
        raise InvalidTransitionError("archived projects cannot be changed")
    if project.status != ProjectStatus.DRAFT:
        locked = sorted(set(data) - EDITABLE_WHILE_ACTIVE)
        if locked:
            raise InvalidTransitionError(
                f"only {', '.join(sorted(EDITABLE_WHILE_ACTIVE))} can change after start",
                [{"field": f, "message": "read-only after start"} for f in locked],
            )
    old_budget = project.budget
    fields = []
    for name, value in data.items():
        if name == "remote_token":
            project.remote_token = crypto.encrypt(value) if value else None
        elif name == "stack":
            if value:
                save_artifact(project, kind=ArtifactKind.STACK, name="stack.yaml", data=value)
                continue
            project.stack = None
        elif name == "process":
            installed = get_process(value)
            if installed is None:
                raise ValidationFailedError(
                    "unknown process", [{"field": "process", "message": f"{value} not installed"}]
                )
            project.process_name, project.process_version = installed.name, installed.version
            fields += ["process_name", "process_version"]
            continue
        elif name == "brief":
            project.brief = value
            save_artifact(project, kind=ArtifactKind.BRIEF, name="brief.md", content=value)
        else:
            setattr(project, name, value)
        fields.append(name)
    project.save(update_fields=[*set(fields), "updated_at"])
    if "budget" in data and Decimal(project.budget) != old_budget:
        emit(
            project,
            "project.budget_changed",
            {"old": old_budget, "new": project.budget},
            actor=user_actor(user),
        )
    return project
