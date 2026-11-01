# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read side for WebSocket clients: access check, snapshot and resync from Postgres."""

import uuid
from typing import Any

from django.contrib.auth.models import AnonymousUser

from dexterhouse.apps.accounts.models import ApiToken, Membership, Scope, User
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.events.schemas import EventEnvelope
from dexterhouse.apps.events.services.publisher import to_envelope

RESYNC_LIMIT = 5_000


def can_read_events(user: User | AnonymousUser | None, token: ApiToken | None) -> bool:
    """Tokens need `events:read`; session users need a membership.

    The per-project organization check arrives with the `projects` app (Sprint 1).
    """
    if user is None or not user.is_authenticated:
        return False
    if token is not None:
        return token.has_scope(Scope.EVENTS_READ)
    return Membership.objects.filter(user=user).exists()


def snapshot(project_id: uuid.UUID) -> dict[str, Any]:
    """Full state for a new client; in Sprint 0 only `last_event_id` is real."""
    last = Event.objects.filter(project_id=project_id).order_by("-created_at", "-id").first()
    return {
        "type": "snapshot",
        "project": {"id": str(project_id)},
        "phases": [],
        "tasks": [],
        "gates_open": [],
        "agents": [],
        "workspace": None,
        "budget": None,
        "last_event_id": str(last.id) if last else None,
    }


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
