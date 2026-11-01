# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prometheus `/metrics` (operations.md): values read from Postgres and Redis at scrape time.

Celery workers and the web processes do not share memory, so counters are derived from the
persisted rows (`LLMCall`, `AgentTurn`, projects, gates) and queue lengths from Redis: every
web replica reports the same numbers. Series:

- `dh_llm_calls_total{provider,model,status}`, `dh_llm_tokens_total{kind}`,
  `dh_llm_cost_eur_total`, `dh_llm_latency_seconds` (histogram, successful calls);
- `dh_agent_turns_total{status}` (`rate(...[1m])*60` = turns per minute);
- `dh_projects{status}`, `dh_gates_open{type}`, `dh_queue_length{queue}`;
- `dh_workspaces_active` (workspaces `ready|busy|idle`), and from the runners' heartbeats
  `dh_runner_up`, `dh_runner_heartbeat_age_seconds`, `dh_runner_exec_total`,
  `dh_runner_exec_seconds_{sum,count}`, `dh_runner_errors_total`, `dh_runner_egress_denied_total`;
- for the alerts (docs/operations.md): `dh_gateway_breaker_open{provider}` (1 while open or
  half-open) and `dh_security_violations_recent` (`security.violation` events, last 10 min).
"""

from collections.abc import Iterator

import redis
import structlog
from django.conf import settings
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    HistogramMetricFamily,
)
from prometheus_client.registry import Collector

logger = structlog.get_logger(__name__)

LATENCY_BUCKETS_S = (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0)
QUEUES = ("agents", "default", "core-callbacks", "runner")
VIOLATIONS_WINDOW_MIN = 10


class DexterHouseCollector(Collector):
    def collect(self) -> Iterator[object]:
        yield from self._llm()
        yield from self._turns()
        yield from self._projects()
        yield self._queues()
        yield from self._runner()
        yield from self._alerts()

    def _alerts(self) -> Iterator[object]:
        from datetime import timedelta

        from django.utils import timezone

        from dexterhouse.apps.events.models import Event
        from dexterhouse.apps.gateway.providers import PROVIDERS
        from dexterhouse.apps.gateway.services.resilience import CircuitBreaker

        breaker = GaugeMetricFamily(
            "dh_gateway_breaker_open", "Provider circuit breaker not closed", labels=["provider"]
        )
        for provider in sorted(PROVIDERS):
            breaker.add_metric([provider], float(CircuitBreaker(provider).state() != "closed"))
        yield breaker
        since = timezone.now() - timedelta(minutes=VIOLATIONS_WINDOW_MIN)
        violations = GaugeMetricFamily(
            "dh_security_violations_recent",
            f"security.violation events in the last {VIOLATIONS_WINDOW_MIN} minutes",
        )
        violations.add_metric(
            [], Event.objects.filter(type="security.violation", created_at__gte=since).count()
        )
        yield violations

    def _runner(self) -> Iterator[object]:
        import time

        from dexterhouse.apps.workspaces.client import runner_heartbeats
        from dexterhouse.apps.workspaces.models import LIVE_STATUSES, Workspace

        workspaces = GaugeMetricFamily("dh_workspaces_active", "Active runner workspaces")
        workspaces.add_metric([], Workspace.objects.filter(status__in=LIVE_STATUSES).count())
        yield workspaces
        beats = runner_heartbeats()
        up = GaugeMetricFamily("dh_runner_up", "Runners with a heartbeat in the last 45 s")
        up.add_metric([], len(beats))
        yield up
        age = GaugeMetricFamily(
            "dh_runner_heartbeat_age_seconds", "Age of the heartbeat", labels=["runner"]
        )
        counters = {
            "exec_total": CounterMetricFamily(
                "dh_runner_exec", "Tool calls run in workspaces", labels=["runner"]
            ),
            "errors_total": CounterMetricFamily(
                "dh_runner_errors", "Runner errors", labels=["runner"]
            ),
            "egress_denied_total": CounterMetricFamily(
                "dh_runner_egress_denied",
                "Workspace requests denied by the proxy",
                labels=["runner"],
            ),
        }
        sums = GaugeMetricFamily(
            "dh_runner_exec_seconds_sum", "Seconds spent in tool calls", labels=["runner"]
        )
        counts = GaugeMetricFamily(
            "dh_runner_exec_seconds_count", "Timed tool calls", labels=["runner"]
        )
        for runner_id, beat in beats.items():
            age.add_metric(
                [runner_id], max(time.time() - float(beat.get("sent_at", time.time())), 0.0)
            )
            values = beat.get("metrics") or {}
            for key, family in counters.items():
                family.add_metric([runner_id], float(values.get(key, 0)))
            sums.add_metric([runner_id], float(values.get("exec_seconds_sum", 0)))
            counts.add_metric([runner_id], float(values.get("exec_seconds_count", 0)))
        yield age
        yield from counters.values()
        yield sums
        yield counts

    def _llm(self) -> Iterator[object]:
        from dexterhouse.apps.gateway.models import LLMCall

        calls = CounterMetricFamily(
            "dh_llm_calls",
            "LLM calls by provider, model and status",
            labels=["provider", "model", "status"],
        )
        for row in LLMCall.objects.values("provider", "model", "status").annotate(n=Count("id")):
            calls.add_metric([row["provider"], row["model"], row["status"]], row["n"])
        yield calls
        ok = LLMCall.objects.filter(status="ok")
        sums = ok.aggregate(
            input=Sum("input_tokens"),
            output=Sum("output_tokens"),
            cached=Sum("cached_tokens"),
            cost=Sum("cost"),
            latency=Sum("latency_ms"),
            n=Count("id"),
            **{
                f"le_{i}": Count("id", filter=Q(latency_ms__lte=int(b * 1000)))
                for i, b in enumerate(LATENCY_BUCKETS_S)
            },
        )
        tokens = CounterMetricFamily("dh_llm_tokens", "LLM tokens by kind", labels=["kind"])
        for kind in ("input", "output", "cached"):
            tokens.add_metric([kind], sums[kind] or 0)
        yield tokens
        cost = CounterMetricFamily("dh_llm_cost_eur", "EUR spent on LLM calls")
        cost.add_metric([], float(sums["cost"] or 0))
        yield cost
        latency = HistogramMetricFamily("dh_llm_latency_seconds", "Latency of successful LLM calls")
        buckets = [(str(b), sums[f"le_{i}"]) for i, b in enumerate(LATENCY_BUCKETS_S)]
        latency.add_metric(
            [], [*buckets, ("+Inf", sums["n"])], sum_value=(sums["latency"] or 0) / 1000
        )
        yield latency

    def _turns(self) -> Iterator[object]:
        from dexterhouse.apps.agents.models import AgentTurn

        turns = CounterMetricFamily("dh_agent_turns", "Agent turns by status", labels=["status"])
        for row in AgentTurn.objects.values("status").annotate(n=Count("id")):
            turns.add_metric([row["status"]], row["n"])
        yield turns

    def _projects(self) -> Iterator[object]:
        from dexterhouse.apps.projects.models import Project
        from dexterhouse.apps.workflows.models import Gate

        projects = GaugeMetricFamily("dh_projects", "Projects by status", labels=["status"])
        for row in Project.objects.values("status").annotate(n=Count("id")):
            projects.add_metric([row["status"]], row["n"])
        yield projects
        gates = GaugeMetricFamily("dh_gates_open", "Open gates by type", labels=["type"])
        for row in Gate.objects.filter(status="open").values("type").annotate(n=Count("id")):
            gates.add_metric([row["type"]], row["n"])
        yield gates

    def _queues(self) -> object:
        family = GaugeMetricFamily("dh_queue_length", "Celery queue length", labels=["queue"])
        try:
            client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=2)
            for queue in QUEUES:
                family.add_metric([queue], client.llen(queue))
        except (redis.RedisError, ValueError) as exc:
            logger.warning("metrics.queue_length_failed", error=str(exc))
        return family


def registry() -> CollectorRegistry:
    reg = CollectorRegistry(auto_describe=False)
    reg.register(DexterHouseCollector())
    return reg


@require_GET
def metrics(request: HttpRequest) -> HttpResponse:
    """Prometheus text format; served on the internal network only (nginx does not proxy it)."""
    return HttpResponse(generate_latest(registry()), content_type=CONTENT_TYPE_LATEST)
