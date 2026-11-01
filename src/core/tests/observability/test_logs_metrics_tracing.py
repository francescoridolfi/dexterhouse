# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured logs, Prometheus metrics, optional OpenTelemetry tracing (F-012)."""

import json
import logging

import pytest
import structlog

from dexterhouse.apps.observability import log, tracing
from dexterhouse.apps.observability.metrics import registry

pytestmark = pytest.mark.django_db


def render(record_event: str, **fields) -> dict:
    formatter = log.formatter("json")
    record = logging.LogRecord(
        "dexterhouse.test", logging.INFO, __file__, 1, record_event, (), None
    )
    with structlog.contextvars.bound_contextvars(**fields):
        return json.loads(formatter.format(record))


def test_json_logs_carry_context_and_redact_secrets():
    line = render("hello", project_id="p1", agent_turn_id="t1", trace_id="abc")
    assert line["event"] == "hello"
    assert (line["project_id"], line["agent_turn_id"], line["trace_id"]) == ("p1", "t1", "abc")
    assert line["service"] == "core"
    assert line["level"] == "info"
    assert "ts" in line
    event = log.redact(
        None,
        "info",
        {"api_key": "x", "input_tokens": 5, "detail": "Bearer abc.def sk-1234567890abcdef"},
    )
    assert event["api_key"] == "***"
    assert event["input_tokens"] == 5
    assert "abc.def" not in event["detail"]
    assert "sk-1234" not in event["detail"]
    assert log.logging_config("INFO", "console")["formatters"]["structured"]["fmt"] == "console"
    assert isinstance(log.renderer("console"), structlog.dev.ConsoleRenderer)


def test_request_middleware_echoes_request_id(client, project, caplog):
    response = client.get(f"/api/v1/projects/{project.id}", HTTP_X_REQUEST_ID="req-12345678")
    assert response["X-Request-ID"] == "req-12345678"
    generated = client.get("/api/v1/projects", HTTP_X_REQUEST_ID="bad id")
    assert len(generated["X-Request-ID"]) == 32

    def access_lines():
        dicts = (r.msg for r in caplog.records if isinstance(r.msg, dict))
        return [m for m in dicts if m.get("event") == "http.request"]

    first = access_lines()[0]
    assert (first["status"], first["project_id"]) == (200, str(project.id))
    client.get("/health/live")  # probes stay out of the access log
    assert len(access_lines()) == 2


def test_metrics_endpoint(client, project, make_call, started):
    make_call(project, "0.3", latency_ms=700)
    make_call(project, None, status="error")
    started()
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.content.decode()
    assert 'dh_llm_calls_total{model="fake-model",provider="fake",status="ok"} 1.0' in text
    assert 'dh_llm_latency_seconds_bucket{le="1.0"} 1.0' in text
    assert "dh_llm_cost_eur_total 0.3" in text
    assert 'dh_projects{status="running"}' in text or 'dh_projects{status="waiting"}' in text
    assert "dh_workspaces_active 0.0" in text
    assert "dh_queue_length" in text


def test_queue_length_reads_redis(settings):
    settings.CELERY_BROKER_URL = settings.REDIS_URL
    names = {m.name: m for m in registry().collect()}
    queues = {s.labels["queue"] for s in names["dh_queue_length"].samples}
    assert queues == {"agents", "default", "core-callbacks", "runner"}


def test_tracing_disabled_is_a_no_op():
    assert not tracing.enabled()
    with tracing.span("x", a=1):
        assert tracing.current_trace_id("fallback") == "fallback"
    tracing.configure()  # no endpoint: nothing installed


def test_tracing_enabled_records_spans(monkeypatch):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing, "_configured", True)
    monkeypatch.setattr(tracing, "_tracer", lambda: provider.get_tracer("t"))
    import uuid

    turn = uuid.uuid4()
    with tracing.turn_context(uuid.uuid4(), turn) as trace_id:
        assert len(trace_id) == 32
        assert trace_id != str(turn)
        assert structlog.contextvars.get_contextvars()["agent_turn_id"] == str(turn)
        with tracing.span("llm.call", provider="fake"):
            pass
    assert [s.name for s in exporter.get_finished_spans()] == ["llm.call", "agent.turn"]
    assert trace.get_tracer_provider() is not None


def test_configure_installs_otlp_exporter(monkeypatch):
    from opentelemetry import trace

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    monkeypatch.setattr(tracing, "_configured", False)
    installed = {}
    monkeypatch.setattr(trace, "set_tracer_provider", lambda p: installed.setdefault("p", p))
    tracing.configure()
    assert tracing._configured is True
    assert installed["p"].resource.attributes["service.name"] == "dexterhouse-core"
    installed["p"].shutdown()
    monkeypatch.setattr(tracing, "_configured", False)


def test_celery_tasks_log_with_their_id():
    from dexterhouse.apps.observability.tasks import rollup_llm_calls

    seen = {}
    original = log._unbind_task

    def capture(**kwargs):
        seen.update(structlog.contextvars.get_contextvars())
        original(**kwargs)

    from celery.signals import task_postrun

    task_postrun.disconnect(dispatch_uid="dh-log-task-postrun")
    task_postrun.connect(capture, weak=False, dispatch_uid="dh-log-task-postrun")
    try:
        rollup_llm_calls.delay()
    finally:
        task_postrun.disconnect(dispatch_uid="dh-log-task-postrun")
        log.connect_celery()
    assert seen["task_name"] == "dexterhouse.apps.observability.tasks.rollup_llm_calls"
    assert seen["task_id"]
    assert "task_id" not in structlog.contextvars.get_contextvars()
