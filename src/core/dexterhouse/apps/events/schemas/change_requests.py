# SPDX-License-Identifier: AGPL-3.0-or-later
"""change_request.* and project.reopened payloads (docs/specs/change-requests.md).

Contract: contracts/events/change_requests.md.
"""

import uuid
from decimal import Decimal

from dexterhouse.apps.events.schemas.base import EventPayload


class _ChangeRequestEvent(EventPayload):
    change_request_id: uuid.UUID
    number: int


class ChangeRequestCreated(_ChangeRequestEvent):
    event_type = "change_request.created"
    actors = ("user",)

    title: str
    budget: Decimal


class ChangeRequestUpdated(_ChangeRequestEvent):
    event_type = "change_request.updated"
    actors = ("user",)

    fields: list[str]


class ChangeRequestQueued(_ChangeRequestEvent):
    event_type = "change_request.queued"
    actors = ("user",)


class ChangeRequestStarted(_ChangeRequestEvent):
    event_type = "change_request.started"
    actors = ("user", "system")

    iteration: int
    process_run_id: uuid.UUID


class ChangeRequestCompleted(_ChangeRequestEvent):
    event_type = "change_request.completed"

    iteration: int


class ChangeRequestFailed(_ChangeRequestEvent):
    event_type = "change_request.failed"

    iteration: int
    error_code: str | None = None


class ChangeRequestCancelled(_ChangeRequestEvent):
    event_type = "change_request.cancelled"
    actors = ("user",)


class ProjectReopened(EventPayload):
    event_type = "project.reopened"
    actors = ("user", "system")

    change_request: uuid.UUID
    number: int
    iteration: int
