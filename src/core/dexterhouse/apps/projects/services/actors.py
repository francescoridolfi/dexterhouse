# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event actors used by the project and workflow services."""

import uuid
from typing import Any

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.events.schemas import Actor
from dexterhouse.apps.events.services import publisher

SYSTEM = Actor(type="system", name="engine")


def user_actor(user: User) -> Actor:
    return Actor(type="user", id=user.id, name=user.get_username())


def agent_actor(agent_id: uuid.UUID, role: str) -> Actor:
    return Actor(type="agent", id=agent_id, name=role)


def emit(
    project: Any,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    actor: Actor = SYSTEM,
    correlation_id: uuid.UUID | None = None,
) -> None:
    """Emit a project event in the caller's transaction (outbox)."""
    publisher.emit(
        event_type,
        organization_id=project.organization_id,
        project_id=project.id,
        actor=actor,
        payload=payload or {},
        correlation_id=correlation_id,
    )
