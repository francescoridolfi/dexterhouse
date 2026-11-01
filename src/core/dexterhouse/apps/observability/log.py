# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured JSON logs (operations.md): `ts, level, service, logger, event, trace_id,
project_id, agent_turn_id, request_id`, secrets redacted.

`LOGGING` in settings routes stdlib records through `ProcessorFormatter`; structlog loggers
share the same processors, so Django, Celery and app logs all come out in one format.
"""

import logging
import re
from typing import Any

import structlog

from dexterhouse.apps.observability.tracing import service_name

REDACTED = "***"
SECRET_KEYS = re.compile(r"(api[_-]?key|(^|_)token$|secret|password|authorization|cookie)", re.I)
SECRET_VALUES = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|Bearer\s+\S+)")
CONTEXT_KEYS = ("trace_id", "project_id", "agent_turn_id", "request_id")


def redact(_logger: Any, _method: str, event: dict[str, Any]) -> dict[str, Any]:
    """Mask secret-looking keys and values (processor)."""
    for key, value in list(event.items()):
        if SECRET_KEYS.search(key) and key not in ("event",):
            event[key] = REDACTED
        elif isinstance(value, str):
            event[key] = SECRET_VALUES.sub(REDACTED, value)
    return event


def add_service(_logger: Any, _method: str, event: dict[str, Any]) -> dict[str, Any]:
    event.setdefault("service", service_name())
    for key in CONTEXT_KEYS:
        event.setdefault(key, None)
    return event


def shared_processors() -> list[Any]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        add_service,
        redact,
    ]


def renderer(fmt: str) -> Any:
    if fmt == "console":
        return structlog.dev.ConsoleRenderer(colors=False)
    return structlog.processors.JSONRenderer()


def formatter(fmt: str = "json") -> logging.Formatter:
    """`ProcessorFormatter` for the stdlib handlers (`LOGGING["formatters"]`)."""
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer(fmt),
        ],
    )


def configure_structlog() -> None:
    """structlog loggers hand their events to stdlib, rendered by `formatter()`."""
    structlog.configure(
        processors=[
            *shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def logging_config(level: str, fmt: str) -> dict[str, Any]:
    """The `LOGGING` dict used by settings."""
    configure_structlog()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {"()": "dexterhouse.apps.observability.log.formatter", "fmt": fmt}
        },
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structured"}},
        "root": {"handlers": ["console"], "level": level},
        "loggers": {"celery": {"level": level, "propagate": True}},
    }


def _bind_task(task_id: str | None = None, task: Any = None, **_: Any) -> None:
    structlog.contextvars.bind_contextvars(task_id=task_id, task_name=getattr(task, "name", None))


def _unbind_task(**_: Any) -> None:
    # Only the task keys: an eager task inside a request keeps the request's context.
    structlog.contextvars.unbind_contextvars("task_id", "task_name")


def connect_celery() -> None:
    """Every Celery task logs with its `task_id` and `task_name`."""
    from celery.signals import task_postrun, task_prerun

    task_prerun.connect(_bind_task, weak=False, dispatch_uid="dh-log-task-prerun")
    task_postrun.connect(_unbind_task, weak=False, dispatch_uid="dh-log-task-postrun")
