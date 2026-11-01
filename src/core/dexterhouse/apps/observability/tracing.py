# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional OpenTelemetry tracing (F-012): on when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

Without the variable every helper is a no-op and no exporter is created. Spans: one per
HTTP request (middleware), per agent turn (`turn_context`) and per LLM call (gateway).
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog
from opentelemetry import trace

logger = structlog.get_logger(__name__)
_configured = False


def enabled() -> bool:
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))


def configure() -> None:
    """Install the OTLP/HTTP exporter once per process (idempotent)."""
    global _configured
    if _configured or not enabled():
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service = os.environ.get("OTEL_SERVICE_NAME") or f"dexterhouse-{service_name()}"
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured = True
    logger.info("tracing.configured", service=service)


def service_name() -> str:
    return os.environ.get("DH_SERVICE", "core")


def _tracer() -> trace.Tracer:
    return trace.get_tracer("dexterhouse")


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    """A span when tracing is on; nothing otherwise."""
    if not _configured:
        yield
        return
    clean = {k: str(v) for k, v in attributes.items() if v is not None}
    with _tracer().start_as_current_span(name, attributes=clean):
        yield


def current_trace_id(default: str = "") -> str:
    """Hex trace id of the active span, or `default` when tracing is off."""
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else default


@contextmanager
def turn_context(project_id: uuid.UUID, turn_id: uuid.UUID) -> Iterator[str]:
    """Span + log context for one agent turn; yields the trace id used in logs and LLMCall."""
    with span("agent.turn", project_id=project_id, agent_turn_id=turn_id):
        trace_id = current_trace_id(str(turn_id))
        with structlog.contextvars.bound_contextvars(
            project_id=str(project_id), agent_turn_id=str(turn_id), trace_id=trace_id
        ):
            yield trace_id
