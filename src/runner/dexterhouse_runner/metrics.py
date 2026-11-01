# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prometheus metrics of the runner (operations.md, section Runner) on `RUNNER_METRICS_PORT`.

The heartbeat also carries a snapshot of them to the core, whose `/metrics` re-exports
`dh_workspaces_active` and `dh_runner_*` (the runner is not on the scrape network in every
deployment).
"""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

WORKSPACES = Gauge("runner_workspaces_active", "Workspace containers of this runner")
EXECS = Counter("runner_exec", "Tool calls run in workspaces", ["tool", "status"])
EXEC_SECONDS = Histogram(
    "runner_exec_duration_seconds",
    "Duration of tool calls in workspaces",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 900),
)
ERRORS = Counter("runner_errors", "Tool and system call errors by code", ["code"])
EGRESS_DENIED = Counter("runner_egress_denied", "Requests from workspaces denied by the proxy")
SYSTEM = Counter(
    "runner_system_calls", "System actions (branch, merge, deliver, exit)", ["action", "status"]
)


def serve(port: int) -> None:
    if port:
        start_http_server(port)


def snapshot() -> dict[str, float]:
    """The heartbeat's copy of the counters (summed over labels)."""

    def total(metric: Counter) -> float:
        return sum(
            s.value for m in metric.collect() for s in m.samples if s.name.endswith("_total")
        )

    exec_count = sum(
        s.value for m in EXEC_SECONDS.collect() for s in m.samples if s.name.endswith("_count")
    )
    exec_sum = sum(
        s.value for m in EXEC_SECONDS.collect() for s in m.samples if s.name.endswith("_sum")
    )
    return {
        "exec_total": total(EXECS),
        "exec_seconds_sum": exec_sum,
        "exec_seconds_count": exec_count,
        "errors_total": total(ERRORS),
        "egress_denied_total": total(EGRESS_DENIED),
    }
