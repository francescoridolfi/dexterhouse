# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event envelope and the payload base class with its type registry (contracts/events)."""

import uuid
from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

ActorType = Literal["agent", "user", "system"]


class UnknownEventTypeError(LookupError):
    """The event type is not in the catalogue."""


class Actor(BaseModel):
    """Who caused the event."""

    model_config = ConfigDict(extra="forbid")

    type: ActorType
    id: uuid.UUID | None = None
    name: str | None = None


class EventPayload(BaseModel):
    """Base of every event payload; subclasses set `event_type` and are registered.

    Producers are strict (`extra="forbid"`): consumers such as the frontend must ignore unknown
    fields instead. Adding an optional field keeps `schema_version`; removing or retyping one
    bumps it.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: ClassVar[str] = ""
    schema_version: ClassVar[int] = 1
    persisted: ClassVar[bool] = True
    actors: ClassVar[tuple[ActorType, ...]] = ("system",)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if cls.event_type:
            if cls.event_type in EVENT_TYPES:
                raise ValueError(f"duplicate event type {cls.event_type}")
            EVENT_TYPES[cls.event_type] = cls


EVENT_TYPES: dict[str, type[EventPayload]] = {}


def payload_model(event_type: str) -> type[EventPayload]:
    """Return the payload model registered for `event_type`."""
    try:
        return EVENT_TYPES[event_type]
    except KeyError:
        raise UnknownEventTypeError(event_type) from None


class EventEnvelope(BaseModel):
    """What goes on Redis, over WebSocket and out of the REST API."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    type: str
    schema_version: int
    organization_id: uuid.UUID
    project_id: uuid.UUID
    actor: Actor
    correlation_id: uuid.UUID
    created_at: datetime
    payload: dict[str, Any]
