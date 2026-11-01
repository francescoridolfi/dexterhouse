# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery task of the agents queue: load the id, call the service, handle retries."""

import uuid
from typing import Any

from celery import shared_task

from dexterhouse.apps.agents.models import AgentTurn, TurnError
from dexterhouse.apps.agents.services.turns import (
    AgentTurnFailedError,
    TransientTurnError,
    fail_turn,
    notify_retry,
    run_turn,
)

MAX_RETRIES = 5
MAX_COUNTDOWN_S = 120


@shared_task(
    bind=True,
    name="dexterhouse.apps.agents.tasks.run_turn",
    queue="agents",
    acks_late=True,  # a killed worker leaves the message unacked: it is redelivered and resumes
    reject_on_worker_lost=True,
    max_retries=MAX_RETRIES,
)
def run_turn_task(self: Any, turn_id: str) -> dict[str, Any] | None:
    """Run or resume a turn; returns the TurnOutput as JSON, or None if the turn failed."""
    AgentTurn.objects.filter(id=turn_id).update(celery_task_id=self.request.id or "")
    try:
        return run_turn(uuid.UUID(turn_id)).model_dump(mode="json")
    except AgentTurnFailedError:
        return None
    except TransientTurnError as exc:
        if self.request.retries >= MAX_RETRIES:
            fail_turn(uuid.UUID(turn_id), TurnError.PROVIDER, f"retries exhausted: {exc}")
            return None
        notify_retry(uuid.UUID(turn_id), str(exc))
        raise self.retry(
            exc=exc, countdown=min(MAX_COUNTDOWN_S, 10 * 2**self.request.retries)
        ) from exc
