# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read side for WebSocket clients: access check, snapshot and resync from Postgres."""

import uuid
from typing import Any, Literal

from django.contrib.auth.models import AnonymousUser

from dexterhouse.apps.accounts.models import ApiToken, Membership, Scope, User
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.events.schemas import EventEnvelope
from dexterhouse.apps.events.services.publisher import to_envelope
from dexterhouse.apps.projects.models import Project
from dexterhouse.apps.projects.services.snapshot import build_snapshot

RESYNC_LIMIT = 5_000


def access(
    user: User | AnonymousUser | None, token: ApiToken | None, project_id: uuid.UUID
) -> Literal["ok", "unauthorized", "forbidden", "not_found"]:
    """Who may follow `/ws/projects/{id}`: members of the project's organization.

    Tokens also need `events:read` and must belong to that organization.
    """
    if user is None or not user.is_authenticated:
        return "unauthorized"
    project = Project.objects.filter(pk=project_id).only("organization_id").first()
    if project is None:
        return "not_found"
    if token is not None:
        ok = token.has_scope(Scope.EVENTS_READ) and token.organization_id == project.organization_id
        return "ok" if ok else "forbidden"
    member = Membership.objects.filter(user=user, organization_id=project.organization_id)
    return "ok" if member.exists() else "forbidden"


def snapshot(project_id: uuid.UUID) -> dict[str, Any]:
    """Full state for a new client (same payload as `GET /projects/{id}/snapshot`)."""
    return build_snapshot(
        Project.objects.select_related("organization", "created_by").get(pk=project_id)
    )


def events_since(project_id: uuid.UUID, since_event_id: uuid.UUID) -> list[EventEnvelope] | None:
    """Events after `since_event_id` in order, or None when a snapshot is needed instead."""
    anchor = Event.objects.filter(project_id=project_id, id=since_event_id).first()
    if anchor is None:
        return None
    rows = list(
        Event.objects.filter(project_id=project_id, created_at__gte=anchor.created_at)
        .exclude(id=anchor.id)
        .order_by("created_at", "id")[: RESYNC_LIMIT + 1]
    )
    if len(rows) > RESYNC_LIMIT:
        return None
    return [to_envelope(row) for row in rows]
