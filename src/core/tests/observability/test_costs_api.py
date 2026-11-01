# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cost aggregates, estimates, organization budget/usage and the roll-up (F-012)."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.observability.models import LLMUsageDaily
from dexterhouse.apps.observability.services import costs, estimate, rollup
from dexterhouse.apps.projects.models import Project

pytestmark = pytest.mark.django_db


def test_costs_endpoint_shapes(client, project, make_call):
    make_call(project, "0.4")
    make_call(project, "0.1", provider="anthropic", model="claude-haiku-5-5")
    make_call(project, None, status="error", error_detail="boom")
    body = client.get(f"/api/v1/projects/{project.id}/costs").json()
    assert body["currency"] == "EUR"
    assert [p["provider"] for p in body["by_provider"]] == ["fake", "anthropic"]
    fake = body["by_provider"][0]
    assert (fake["calls"], fake["errors"], fake["cost"]) == (2, 1, "0.400000")
    assert body["by_phase"] == [
        {"phase_run": None, "phase_id": None, "calls": 2, "turns": 0, "cost": "0.500000",
         "input_tokens": 200, "output_tokens": 100, "cached_tokens": 0}
    ]  # fmt: skip
    assert body["by_agent"][0]["agent_id"] is None
    assert body["by_task"] == []
    assert body["by_day"] == [
        {"day": timezone.localdate().isoformat(), "calls": 2, "cost": "0.500000"}
    ]
    assert body["estimate"] == {"low": 8.0, "high": 25.0, "basis": "static", "currency": "EUR"}


def test_llm_calls_are_paginated_and_filtered(client, project, make_call):
    for _ in range(3):
        make_call(project)
    make_call(project, None, status="timeout")
    url = f"/api/v1/projects/{project.id}/llm-calls"
    page = client.get(url, {"limit": 2}).json()
    assert len(page["results"]) == 2
    assert page["next"]
    timeouts = client.get(url, {"status": "timeout"}).json()["results"]
    assert [c["status"] for c in timeouts] == ["timeout"]
    assert timeouts[0]["cost"] is None


def test_estimate_static_scales_with_brief_and_uses_history(client, organization, user, project):
    assert estimate.estimate(organization.id, "code-review-only", 100)["high"] == 5.0
    assert estimate.estimate(organization.id, "unknown", 4_000) == {
        "low": 10.0, "high": 40.0, "basis": "static", "currency": "EUR"
    }  # fmt: skip
    body = client.get(
        "/api/v1/estimate", {"process": "software-house-default", "brief_chars": "4000"}
    )
    assert body.json()["high"] == 50.0
    assert client.get("/api/v1/estimate", {"brief_chars": "x"}).status_code == 400
    for i in range(10):
        Project.objects.create(
            organization=organization, name=f"p{i}", slug=f"p{i}", brief="b" * 2000,
            process_name="software-house-default", process_version="1.0.0", budget=50,
            spent=Decimal(10 + i), status="completed", completed_at=timezone.now(),
            created_by=user,
        )  # fmt: skip
    guess = client.get(f"/api/v1/projects/{project.id}/estimate").json()
    assert guess["basis"] == "history"
    assert guess["low"] == 14.5
    assert guess["high"] >= guess["low"]


def test_organization_budget_and_usage(client, organization, project, make_call, make_member):
    make_call(project, "1.25")
    assert client.get("/api/v1/organization/budget").json()["budget_monthly"] is None
    response = client.put("/api/v1/organization/budget", {"budget_monthly": "100"}, format="json")
    assert response.json()["budget_monthly"] == "100.000000"
    assert response.json()["spent_month"] == "1.250000"
    assert (
        client.put(
            "/api/v1/organization/budget", {"budget_monthly": "-1"}, format="json"
        ).status_code
        == 400
    )
    month = timezone.localdate().strftime("%Y-%m")
    usage = client.get("/api/v1/organization/usage", {"month": month}).json()
    assert usage["spent"] == "1.250000"
    assert usage["projects"][0]["name"] == "GymBook"
    assert usage["tokens"] == {"input": 100, "output": 50, "cached": 0}
    assert client.get("/api/v1/organization/usage", {"month": "2026-13"}).status_code == 400
    december = client.get("/api/v1/organization/usage", {"month": "2025-12"}).json()
    assert december["calls"] == 0
    assert make_member("member").get("/api/v1/organization/budget").status_code == 403


def test_rollup_keeps_totals(project, make_call, organization):
    old = make_call(project, "2", input_tokens=10, output_tokens=5)
    make_call(project, None, input_tokens=3, output_tokens=4)
    make_call(project, "0.5")
    past = timezone.now() - timedelta(days=200)
    LLMCall.objects.exclude(pk__in=LLMCall.objects.order_by("-created_at")[:1]).update(
        created_at=past
    )
    before = costs.project_totals(project.id)
    assert rollup.rollup() == 2
    assert LLMCall.objects.filter(project=project).count() == 1
    daily = LLMUsageDaily.objects.get(project=project)
    assert (daily.calls, daily.unpriced_tokens, daily.cost) == (2, 7, Decimal("2"))
    assert costs.project_totals(project.id) == before
    assert costs.by_provider(project.id)[0]["calls"] == 3
    assert sum(Decimal(d["cost"]) for d in costs.by_day(project.id)) == Decimal("2.5")
    assert old.pk  # rolled-up rows are gone, the aggregate remains
    out = StringIO()
    call_command("costs", "rollup", "--months", "6", stdout=out)
    assert "rolled up 0 calls" in out.getvalue()
    call_command("costs", "refresh", stdout=out)
    project.refresh_from_db()
    assert project.spent == Decimal("2.5")


def test_rollup_task(project, make_call):
    from dexterhouse.apps.observability.tasks import rollup_llm_calls

    make_call(project)
    assert rollup_llm_calls() == 0
