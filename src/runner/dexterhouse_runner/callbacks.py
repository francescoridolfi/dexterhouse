# SPDX-License-Identifier: AGPL-3.0-or-later
"""Callbacks to the core on `core-callbacks` (CD-021): the runner never writes events."""

from typing import Any

import structlog

from dexterhouse_schema.runner import (
    CALLBACK_QUEUE,
    Heartbeat,
    Message,
    SecretsBlocked,
    WorkspaceChanged,
)

logger = structlog.get_logger(__name__)


class Callbacks:
    def __init__(self, app: Any) -> None:
        self.app = app

    def send(self, task: str, message: Message) -> None:
        try:
            self.app.send_task(task, args=[message.dump()], queue=CALLBACK_QUEUE)
        except Exception as exc:  # the broker is down: the core reconciles on the next heartbeat
            logger.warning("runner.callback_failed", task=task, error=str(exc))

    def workspace_changed(self, message: WorkspaceChanged) -> None:
        self.send("core.runner.workspace_changed", message)

    def heartbeat(self, message: Heartbeat) -> None:
        self.send("core.runner.heartbeat", message)

    def secrets_blocked(self, message: SecretsBlocked) -> None:
        self.send("core.runner.secrets_blocked", message)
