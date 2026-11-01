# SPDX-License-Identifier: AGPL-3.0-or-later
"""notification.* payloads (contracts/events/notifications.md, E-06)."""

import uuid
from typing import Literal

from dexterhouse.apps.events.schemas.base import EventPayload


class NotificationCreated(EventPayload):
    """An in-app notification for one user (bell in 3D, badge in 2D); the UI filters by user."""

    event_type = "notification.created"

    notification_id: uuid.UUID
    user_id: uuid.UUID
    kind: Literal["gate_opened", "gate_reminder"]
    title: str
    gate_id: uuid.UUID | None = None
    gate_type: Literal["approval", "question", "escalation"] | None = None
