# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-request log context (`request_id`, `trace_id`, `project_id`), an optional span and the
access log: one JSON line per request (uvicorn runs with `--no-access-log`)."""

import re
import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from django.http import HttpRequest, HttpResponse

from dexterhouse.apps.observability import tracing

REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
QUIET_PATHS = ("/health/", "/metrics")  # probes and scrapes: logged only when they fail
logger = structlog.get_logger("dexterhouse.http")


class RequestContextMiddleware:
    """Binds the log context for the request and echoes `X-Request-ID`."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if REQUEST_ID.match(incoming) else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        started = time.monotonic()
        with tracing.span("http.request", method=request.method, path=request.path):
            structlog.contextvars.bind_contextvars(
                request_id=request_id, trace_id=tracing.current_trace_id(request_id)
            )
            response = self.get_response(request)
        response["X-Request-ID"] = request_id
        if response.status_code >= 500 or not request.path.startswith(QUIET_PATHS):
            log = logger.error if response.status_code >= 500 else logger.info
            log(
                "http.request",
                method=request.method,
                path=request.path,
                status=response.status_code,
                duration_ms=round((time.monotonic() - started) * 1000, 1),
            )
        structlog.contextvars.clear_contextvars()
        return response

    def process_view(self, request: HttpRequest, view: Any, args: Any, kwargs: Any) -> None:
        if "project_id" in kwargs:
            structlog.contextvars.bind_contextvars(project_id=str(kwargs["project_id"]))
