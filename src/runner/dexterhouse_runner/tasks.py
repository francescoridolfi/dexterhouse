# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery application of the runner: the `runner` queue (infra/runner_protocol.md).

Each task validates its payload (`dexterhouse_schema.runner`), calls `RunnerService` and
returns a `ToolResult` dict through the result backend. A payload of another protocol
`schema` fails validation and is answered with `internal` (operations.md). The worker uses
the threads pool: the MCP sessions of the workspaces live in this one process. On
`worker_ready` a daemon thread sends the heartbeat every `RUNNER_HEARTBEAT_S` and the
Prometheus endpoint starts on `RUNNER_METRICS_PORT`.
"""

import threading
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import redis
import structlog
from celery import Celery
from celery.signals import worker_ready, worker_shutdown
from pydantic import ValidationError

from dexterhouse_runner import metrics
from dexterhouse_runner.callbacks import Callbacks
from dexterhouse_runner.config import get_settings
from dexterhouse_runner.service import RunnerService
from dexterhouse_schema.runner import RUNNER_QUEUE, RUNNER_TASKS, Message, ToolResult

logger = structlog.get_logger(__name__)

settings = get_settings()
app = Celery("dexterhouse_runner")
app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    result_expires=3600,
    task_default_queue=RUNNER_QUEUE,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=1,
    task_acks_late=False,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
)
_stop = threading.Event()


@lru_cache(maxsize=1)
def service() -> RunnerService:
    from dexterhouse_runner.docker_manager import DockerManager
    from dexterhouse_runner.sessions import SessionPool

    return RunnerService(
        settings,
        DockerManager(settings),
        SessionPool(settings.DOCKER_CLI),
        Callbacks(app),
        redis.Redis.from_url(settings.REDIS_URL),
    )


def _handle(name: str, method: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    model: type[Message] = RUNNER_TASKS[name]

    def run(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            message = model.model_validate(payload)
        except ValidationError as exc:
            logger.warning("runner.invalid_payload", task=name, errors=exc.errors()[:3])
            return ToolResult.failure("internal", f"invalid {name} payload: {exc}").dump()
        result: ToolResult = getattr(service(), method)(message)
        return result.dump()

    run.__name__ = method
    return run


for _name, _method in {
    "runner.workspace.create": "create",
    "runner.workspace.destroy": "destroy",
    "runner.workspace.status": "status",
    "runner.tool.invoke": "invoke",
    "runner.tool.list": "list_tools",
    "runner.system.branch_create": "branch_create",
    "runner.system.merge": "merge",
    "runner.system.deliver": "deliver",
    "runner.system.exit_check": "exit_check",
    "runner.system.commit_log": "commit_log",
    "runner.system.tree": "tree",
}.items():
    app.task(name=_name, queue=RUNNER_QUEUE)(_handle(_name, _method))


def _heartbeat_loop() -> None:
    while True:
        try:
            service().heartbeat()
        except Exception as exc:  # Docker or Redis hiccup: try again on the next beat
            logger.warning("runner.heartbeat_failed", error=str(exc))
        if _stop.wait(settings.RUNNER_HEARTBEAT_S):
            return


@worker_ready.connect
def _start(**_: Any) -> None:
    metrics.serve(settings.RUNNER_METRICS_PORT)
    threading.Thread(target=_heartbeat_loop, name="runner-heartbeat", daemon=True).start()
    logger.info("runner.started", runner_id=settings.RUNNER_ID)


@worker_shutdown.connect
def _stop_heartbeat(**_: Any) -> None:
    _stop.set()
