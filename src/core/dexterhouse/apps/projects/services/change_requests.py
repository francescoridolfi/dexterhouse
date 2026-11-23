# SPDX-License-Identifier: AGPL-3.0-or-later
"""Change requests (docs/specs/change-requests.md): CR-n, its states and its queue.

States: `draft -> queued -> running -> completed | failed`, `draft|queued -> cancelled`,
`failed -> running` (retry). Only drafts are editable; at most one CR runs per project.
"""

from typing import Any

from django.db import transaction
from django.db.models import Max

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.observability.services.estimate import estimate
from dexterhouse.apps.projects.models import (
    ChangeRequest,
    ChangeRequestStatus,
    Project,
    ProjectStatus,
)
from dexterhouse.apps.projects.services.actors import emit, user_actor
from dexterhouse.common.errors import InvalidTransitionError, check_transition

CR = ChangeRequestStatus
CR_ALLOWED: dict[str, frozenset[str]] = {
    CR.DRAFT: frozenset({CR.QUEUED, CR.CANCELLED}),
    CR.QUEUED: frozenset({CR.RUNNING, CR.CANCELLED}),
    CR.RUNNING: frozenset({CR.COMPLETED, CR.FAILED}),
    CR.FAILED: frozenset({CR.RUNNING}),
    CR.COMPLETED: frozenset(),
    CR.CANCELLED: frozenset(),
}
EDITABLE = ("title", "body", "budget")


def _lock(cr: ChangeRequest) -> tuple[Project, ChangeRequest]:
    """Project first (the engine's lock order), then the CR row."""
    from dexterhouse.apps.workflows.engine import common

    project, _run = common.lock(cr.project_id)
    row = ChangeRequest.objects.select_for_update().get(pk=cr.pk)
    row.project = project
    return project, row


def _payload(cr: ChangeRequest, **extra: Any) -> dict[str, Any]:
    return {"change_request_id": cr.id, "number": cr.number, **extra}


def set_status(cr: ChangeRequest, target: str, *fields: str) -> None:
    """Validate and apply `cr.status -> target`; the caller emits the event."""
    check_transition("change_request", cr.status, target, CR_ALLOWED)
    cr.status = target
    cr.save(update_fields=["status", *fields, "updated_at"])


def create_change_request(project: Project, user: User, data: dict[str, Any]) -> ChangeRequest:
    """member: a new draft numbered CR-n (n = last number + 1)."""
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project.pk)
        if project.status == ProjectStatus.ARCHIVED:
            raise InvalidTransitionError("archived projects take no change requests")
        last = project.change_requests.aggregate(n=Max("number"))["n"] or 0
        cr = ChangeRequest.objects.create(
            project=project,
            number=last + 1,
            created_by=user,
            **{k: data[k] for k in EDITABLE if k in data},
        )
        payload = _payload(cr, title=cr.title, budget=cr.budget)
        emit(project, "change_request.created", payload, actor=user_actor(user))
    return cr


def update_change_request(cr: ChangeRequest, user: User, data: dict[str, Any]) -> ChangeRequest:
    """PATCH, only in `draft`."""
    with transaction.atomic():
        project, cr = _lock(cr)
        if cr.status != CR.DRAFT:
            raise InvalidTransitionError(f"only drafts can be edited, not {cr.status}")
        fields = sorted(k for k in EDITABLE if k in data)
        for name in fields:
            setattr(cr, name, data[name])
        cr.save(update_fields=[*fields, "updated_at"])
        emit(project, "change_request.updated", _payload(cr, fields=fields), actor=user_actor(user))
    return cr


def queue_change_request(cr: ChangeRequest, user: User) -> ChangeRequest:
    """admin: draft -> queued; starts at once when the project is already `completed`."""
    from dexterhouse.apps.projects.services import iterations

    with transaction.atomic():
        project, cr = _lock(cr)
        if project.status == ProjectStatus.ARCHIVED:
            raise InvalidTransitionError("the project is archived")
        set_status(cr, CR.QUEUED)
        emit(project, "change_request.queued", _payload(cr), actor=user_actor(user))
        iterations.start_next_change_request(project, user)
    cr.refresh_from_db()
    return cr


def cancel_change_request(cr: ChangeRequest, user: User) -> ChangeRequest:
    """admin: draft|queued -> cancelled."""
    with transaction.atomic():
        project, cr = _lock(cr)
        set_status(cr, CR.CANCELLED)
        emit(project, "change_request.cancelled", _payload(cr), actor=user_actor(user))
    return cr


def estimate_change_request(cr: ChangeRequest) -> dict[str, Any]:
    """`{low, high, basis, currency}` for running the project's process on the CR body."""
    project = cr.project
    return estimate(project.organization_id, project.process_name, len(cr.body))
