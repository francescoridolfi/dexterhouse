# SPDX-License-Identifier: AGPL-3.0-or-later
"""`package.*` events (contracts/events/packages_budget_security.md).

Package events belong to an organization, not to a project: they are emitted on the
project that caused them (`install_proposed_packages`) or, otherwise, on the organization
channel, whose `project_id` is the organization id. Global packages (built-in, CLI
without `--org`) have no organization: their changes are only logged.
"""

import uuid
from typing import Any

import structlog

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.events.schemas import Actor, payload_model
from dexterhouse.apps.events.services import publisher

logger = structlog.get_logger(__name__)
SYSTEM = Actor(type="system", name="packages")


def actor_for(user: User | None) -> Actor:
    return Actor(type="user", id=user.id, name=user.get_username()) if user else SYSTEM


def emit(
    event_type: str,
    payload: dict[str, Any],
    *,
    organization_id: uuid.UUID | None,
    project_id: uuid.UUID | None = None,
    user: User | None = None,
) -> None:
    if organization_id is None:
        logger.debug("packages.event", type=event_type, **_loggable(payload))
        return
    actor = actor_for(user)
    if user is not None and "user" not in payload_model(event_type).actors:
        actor = SYSTEM
    publisher.emit(
        event_type,
        organization_id=organization_id,
        project_id=project_id or organization_id,
        actor=actor,
        payload=payload,
    )


def _loggable(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in payload.items()}
