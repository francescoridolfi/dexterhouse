# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event catalogue: importing this package registers every payload model."""

from dexterhouse.apps.events.schemas import (  # noqa: F401  (import registers the models)
    agents,
    notifications,
    packages_budget_security,
    project_process,
    tasks_gates,
    workspace_release,
)
from dexterhouse.apps.events.schemas.base import (
    EVENT_TYPES,
    Actor,
    ActorType,
    EventEnvelope,
    EventPayload,
    UnknownEventTypeError,
    payload_model,
)

__all__ = [
    "EVENT_TYPES",
    "Actor",
    "ActorType",
    "EventEnvelope",
    "EventPayload",
    "UnknownEventTypeError",
    "payload_model",
]
