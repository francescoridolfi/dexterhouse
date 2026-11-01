# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cost aggregates (F-012): per project, phase, task, agent, provider and day, in EUR.

`LLMCall` is the source of truth; calls rolled up into `LLMUsageDaily` (CD-027) still count
for the project total and the provider/day views.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db.models import Count, F, Q, QuerySet, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.gateway.models import CallStatus, LLMCall
from dexterhouse.apps.observability.models import LLMUsageDaily

ZERO = Decimal(0)


def _money(value: Any) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.000001")))


def phase_cost(phase_run_id: uuid.UUID) -> Decimal:
    """Real cost of a phase run: the sum of its agent turns (phase.completed.cost)."""
    total = AgentTurn.objects.filter(phase_run_id=phase_run_id).aggregate(c=Sum("cost"))["c"]
    return total or ZERO


def task_cost(task_id: uuid.UUID) -> Decimal:
    """Real cost of a task and its fix children (task.completed.cost)."""
    rows = AgentTurn.objects.filter(Q(task_id=task_id) | Q(task__parent_id=task_id))
    return rows.aggregate(c=Sum("cost"))["c"] or ZERO


def project_totals(project_id: uuid.UUID) -> tuple[Decimal, int]:
    """(spent EUR, tokens without a known price) from raw calls plus daily roll-ups."""
    calls = LLMCall.objects.filter(project_id=project_id)
    raw = calls.filter(status=CallStatus.OK).aggregate(cost=Sum("cost"))
    unpriced = calls.filter(status=CallStatus.OK, cost__isnull=True).aggregate(
        t=Coalesce(Sum(F("input_tokens") + F("output_tokens")), 0)
    )["t"]
    rolled = LLMUsageDaily.objects.filter(project_id=project_id).aggregate(
        cost=Sum("cost"), unpriced=Coalesce(Sum("unpriced_tokens"), 0)
    )
    spent = (raw["cost"] or ZERO) + (rolled["cost"] or ZERO)
    return spent, int(unpriced) + int(rolled["unpriced"])


def month_start(now: datetime | None = None) -> datetime:
    now = timezone.localtime(now or timezone.now())
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def organization_month_spend(organization_id: uuid.UUID, start: datetime | None = None) -> Decimal:
    """EUR spent by the organization since `start` (default: this calendar month)."""
    start = start or month_start()
    raw = LLMCall.objects.filter(
        organization_id=organization_id, status=CallStatus.OK, created_at__gte=start
    ).aggregate(c=Sum("cost"))["c"]
    rolled = LLMUsageDaily.objects.filter(
        organization_id=organization_id, day__gte=start.date()
    ).aggregate(c=Sum("cost"))["c"]
    return (raw or ZERO) + (rolled or ZERO)


def _token_sums() -> dict[str, Any]:
    return {
        "cost": Sum("cost"),
        "input_tokens": Coalesce(Sum("input_tokens"), 0),
        "output_tokens": Coalesce(Sum("output_tokens"), 0),
        "cached_tokens": Coalesce(Sum("cached_tokens"), 0),
    }


def _tokens(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "cost": _money(row["cost"]),
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "cached_tokens": row["cached_tokens"],
    }


def _ok_calls(project_id: uuid.UUID) -> QuerySet[LLMCall]:
    return LLMCall.objects.filter(project_id=project_id, status=CallStatus.OK)


def by_phase(project_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        _ok_calls(project_id)
        .values(
            phase_run=F("agent_turn__phase_run_id"), phase_id=F("agent_turn__phase_run__phase_id")
        )
        .annotate(calls=Count("id"), turns=Count("agent_turn", distinct=True), **_token_sums())
        .order_by("agent_turn__phase_run__position")
    )
    return [
        {
            "phase_run": str(r["phase_run"]) if r["phase_run"] else None,
            "phase_id": r["phase_id"],
            "calls": r["calls"],
            "turns": r["turns"],
            **_tokens(r),
        }
        for r in rows
    ]


def by_agent(project_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        _ok_calls(project_id)
        .values(
            agent_id=F("agent_turn__agent_instance_id"),
            role=F("agent_turn__agent_instance__role"),
            display_name=F("agent_turn__agent_instance__display_name"),
        )
        .annotate(calls=Count("id"), turns=Count("agent_turn", distinct=True), **_token_sums())
        .order_by("-cost")
    )
    return [
        {
            "agent_id": str(r["agent_id"]) if r["agent_id"] else None,
            "role": r["role"],
            "display_name": r["display_name"],
            "calls": r["calls"],
            "turns": r["turns"],
            **_tokens(r),
        }
        for r in rows
    ]


def by_task(project_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        _ok_calls(project_id)
        .filter(agent_turn__task__isnull=False)
        .values(task_id=F("agent_turn__task_id"), external_id=F("agent_turn__task__external_id"))
        .annotate(calls=Count("id"), **_token_sums())
        .order_by("external_id")
    )
    return [
        {"task_id": str(r["task_id"]), "external_id": r["external_id"], **_tokens(r)} for r in rows
    ]


def by_provider(project_id: uuid.UUID | None = None, *, organization_id=None, since=None):
    """Per provider/model, raw calls (all statuses) merged with the daily roll-ups."""
    calls = LLMCall.objects.all()
    rolled = LLMUsageDaily.objects.all()
    if project_id is not None:
        calls, rolled = calls.filter(project_id=project_id), rolled.filter(project_id=project_id)
    if organization_id is not None:
        calls = calls.filter(organization_id=organization_id)
        rolled = rolled.filter(organization_id=organization_id)
    if since is not None:
        calls, rolled = calls.filter(created_at__gte=since), rolled.filter(day__gte=since.date())
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for r in calls.values("provider", "model").annotate(
        calls=Count("id"),
        errors=Count("id", filter=~Q(status=CallStatus.OK)),
        latency_ms=Coalesce(Sum("latency_ms", filter=Q(status=CallStatus.OK)), 0),
        **_token_sums(),
    ):
        merged[(r["provider"], r["model"])] = r
    for r in rolled.values("provider", "model").annotate(
        rcalls=Sum("calls"), rerrors=Sum("errors"), **_token_sums()
    ):
        row = merged.setdefault(
            (r["provider"], r["model"]),
            {
                "provider": r["provider"],
                "model": r["model"],
                "calls": 0,
                "errors": 0,
                "latency_ms": 0,
                "cost": ZERO,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
            },
        )
        row["calls"] += r["rcalls"] or 0
        row["errors"] += r["rerrors"] or 0
        row["cost"] = (row["cost"] or ZERO) + (r["cost"] or ZERO)
        for key in ("input_tokens", "output_tokens", "cached_tokens"):
            row[key] += r[key]
    out = []
    for row in sorted(merged.values(), key=lambda r: -(r["cost"] or ZERO)):
        ok = row["calls"] - row["errors"]
        out.append(
            {
                "provider": row["provider"],
                "model": row["model"],
                "calls": row["calls"],
                "errors": row["errors"],
                "avg_latency_ms": int(row["latency_ms"] / ok) if ok > 0 else None,
                **_tokens(row),
            }
        )
    return out


def by_day(project_id: uuid.UUID | None = None, *, organization_id=None, since=None):
    calls = LLMCall.objects.filter(status=CallStatus.OK)
    rolled = LLMUsageDaily.objects.all()
    if project_id is not None:
        calls, rolled = calls.filter(project_id=project_id), rolled.filter(project_id=project_id)
    if organization_id is not None:
        calls = calls.filter(organization_id=organization_id)
        rolled = rolled.filter(organization_id=organization_id)
    if since is not None:
        calls, rolled = calls.filter(created_at__gte=since), rolled.filter(day__gte=since.date())
    days: dict[date, dict[str, Any]] = {}
    for r in (
        calls.annotate(d=TruncDate("created_at"))
        .values("d")
        .annotate(calls=Count("id"), cost=Sum("cost"))
    ):
        days[r["d"]] = {"calls": r["calls"], "cost": r["cost"] or ZERO}
    for r in rolled.values("day").annotate(calls=Sum("calls"), cost=Sum("cost")):
        row = days.setdefault(r["day"], {"calls": 0, "cost": ZERO})
        row["calls"] += r["calls"] or 0
        row["cost"] += r["cost"] or ZERO
    return [
        {"day": d.isoformat(), "calls": v["calls"], "cost": _money(v["cost"])}
        for d, v in sorted(days.items())
    ]


def project_costs(project: Any) -> dict[str, Any]:
    """`GET /projects/{id}/costs`."""
    from dexterhouse.apps.observability.services.estimate import estimate_for_project

    return {
        "currency": "EUR",
        "budget": _money(project.budget),
        "spent": _money(project.spent),
        "unpriced_tokens": project.spent_unpriced_tokens,
        "estimate": estimate_for_project(project),
        "by_phase": by_phase(project.id),
        "by_agent": by_agent(project.id),
        "by_task": by_task(project.id),
        "by_provider": by_provider(project.id),
        "by_day": by_day(project.id),
    }


def organization_usage(organization: Any, month: date) -> dict[str, Any]:
    """`GET /organization/usage?month=YYYY-MM`."""
    start = timezone.make_aware(datetime(month.year, month.month, 1))
    end = timezone.make_aware(datetime(month.year + (month.month == 12), month.month % 12 + 1, 1))
    calls = LLMCall.objects.filter(
        organization_id=organization.id, created_at__gte=start, created_at__lt=end
    )
    ok = calls.filter(status=CallStatus.OK)
    totals = ok.aggregate(**_token_sums())
    rolled = LLMUsageDaily.objects.filter(
        organization_id=organization.id, day__gte=start.date(), day__lt=end.date()
    ).aggregate(c=Sum("cost"))["c"]
    projects = (
        ok.values("project_id", name=F("project__name"))
        .annotate(cost=Sum("cost"), calls=Count("id"))
        .order_by("-cost")
    )
    return {
        "month": f"{month.year:04d}-{month.month:02d}",
        "currency": "EUR",
        "spent": _money((totals["cost"] or ZERO) + (rolled or ZERO)),
        "budget_monthly": _money(organization.budget_monthly)
        if organization.budget_monthly is not None
        else None,
        "calls": calls.count(),
        "tokens": {
            "input": totals["input_tokens"],
            "output": totals["output_tokens"],
            "cached": totals["cached_tokens"],
        },
        "projects": [
            {
                "project_id": str(p["project_id"]),
                "name": p["name"],
                "calls": p["calls"],
                "cost": _money(p["cost"]),
            }
            for p in projects
        ],
        "by_day": [
            d
            for d in by_day(organization_id=organization.id, since=start)
            if d["day"] < end.date().isoformat()
        ],
    }
