# SPDX-License-Identifier: AGPL-3.0-or-later
"""Emit events: validate, write to Postgres (outbox), publish to Redis after commit."""

import uuid
from datetime import datetime, timedelta
from typing import Any

import redis
import structlog
from django.db import transaction
from django.utils import timezone

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.events.schemas import Actor, EventEnvelope, EventPayload, payload_model
from dexterhouse.apps.events.services import streams
from dexterhouse.common.models import new_id

logger = structlog.get_logger(__name__)


class ActorNotAllowedError(ValueError):
    """The actor type is not one the catalogue allows for this event type."""


def build_envelope(
    event_type: str,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    actor: Actor,
    payload: EventPayload | dict[str, Any],
    correlation_id: uuid.UUID | None = None,
) -> tuple[EventEnvelope, type[EventPayload]]:
    """Validate `payload` against the catalogue and wrap it in an envelope."""
    model = payload_model(event_type)
    if actor.type not in model.actors:
        raise ActorNotAllowedError(f"{event_type} cannot be emitted by {actor.type}")
    data = payload if isinstance(payload, model) else model.model_validate(payload)
    event_id = new_id()
    envelope = EventEnvelope(
        id=event_id,
        type=event_type,
        schema_version=model.schema_version,
        organization_id=organization_id,
        project_id=project_id,
        actor=actor,
        correlation_id=correlation_id or event_id,
        created_at=timezone.now(),
        payload=data.model_dump(mode="json"),
    )
    return envelope, model


def emit(
    event_type: str,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    actor: Actor,
    payload: EventPayload | dict[str, Any],
    correlation_id: uuid.UUID | None = None,
) -> EventEnvelope:
    """Emit an event; persisted types are stored in the caller's transaction (outbox).

    Publication to Redis happens on commit; if Redis is down the row stays `published=false`
    and `republish_pending` retries. Delivery is at-least-once: consumers dedupe by `id`.
    Stream-only types (`agent.speaking`) go straight to Redis and are lost if it is down.
    """
    envelope, model = build_envelope(
        event_type,
        organization_id=organization_id,
        project_id=project_id,
        actor=actor,
        payload=payload,
        correlation_id=correlation_id,
    )
    if not model.persisted:
        _safe_append(envelope)
        return envelope
    with transaction.atomic():
        Event.objects.create(
            id=envelope.id,
            organization_id=envelope.organization_id,
            project_id=envelope.project_id,
            type=envelope.type,
            schema_version=envelope.schema_version,
            actor_type=actor.type,
            actor_id=actor.id,
            actor_name=actor.name or "",
            payload=envelope.payload,
            correlation_id=envelope.correlation_id,
            created_at=envelope.created_at,
        )
        transaction.on_commit(lambda: publish(envelope))
    return envelope


def _safe_append(envelope: EventEnvelope) -> bool:
    try:
        streams.append(envelope)
    except redis.RedisError as exc:
        logger.warning("events.publish_failed", event_id=str(envelope.id), error=str(exc))
        return False
    return True


def publish(envelope: EventEnvelope) -> bool:
    """XADD a persisted event and flag it as published; False if Redis is unavailable."""
    if not _safe_append(envelope):
        return False
    Event.objects.filter(id=envelope.id, created_at=envelope.created_at).update(published=True)
    return True


def to_envelope(event: Event) -> EventEnvelope:
    """Rebuild the envelope of a stored event."""
    return EventEnvelope(
        id=event.id,
        type=event.type,
        schema_version=event.schema_version,
        organization_id=event.organization_id,
        project_id=event.project_id,
        actor=Actor(type=event.actor_type, id=event.actor_id, name=event.actor_name or None),
        correlation_id=event.correlation_id,
        created_at=event.created_at,
        payload=event.payload,
    )


def republish_pending(
    *, older_than: timedelta = timedelta(seconds=10), limit: int = 500, now: datetime | None = None
) -> int:
    """Publish rows still flagged unpublished (outbox sweep); returns how many succeeded."""
    cutoff = (now or timezone.now()) - older_than
    pending = Event.objects.filter(published=False, created_at__lte=cutoff).order_by(
        "created_at", "id"
    )[:limit]
    count = 0
    for event in pending:
        if not publish(to_envelope(event)):
            break
        count += 1
    if count:
        logger.info("events.republished", count=count)
    return count
