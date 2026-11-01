# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget end to end with real agent turns and the `fake` provider: the project stops at
100 %, nothing is paid twice, raising the budget resumes it; phase/task events carry the
real cost (sum of the agent turns)."""

from decimal import Decimal

import pytest
from django.db.models import Sum

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.workflows.models import Gate, StepRun
from tests.workflows.conftest import drain, event_types, events
from tests.workflows.test_e2e import create

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("real_runtime")]


def test_budget_pauses_and_resumes_a_real_run(client, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"tasks": 2}
    project = create(client, execution_mode="autonomous", budget="0.004")
    assert client.post(f"/api/v1/projects/{project.id}/start").status_code == 200
    drain(project)

    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "budget")
    assert project.spent >= project.budget
    gate = Gate.objects.get(project=project, gate_id="budget", status="open")
    assert "budget.exceeded" in event_types(project, "budget.")
    calls_at_stop = LLMCall.objects.filter(project=project).count()
    # The next step waits in the queue without having used up an attempt; nothing failed.
    queued = StepRun.objects.get(project=project, status="queued")
    assert queued.attempts == 0
    assert not StepRun.objects.filter(project=project, status="failed").exists()
    drain(project)  # nothing runs while waiting
    assert LLMCall.objects.filter(project=project).count() == calls_at_stop

    response = client.patch(f"/api/v1/projects/{project.id}", {"budget": "20"}, format="json")
    assert response.status_code == 200
    gate.refresh_from_db()
    assert (gate.status, gate.decision) == ("approved", "retry")
    drain(project)

    project.refresh_from_db()
    assert project.status == "completed", event_types(project)[-5:]
    turns = AgentTurn.objects.filter(project=project)
    assert set(turns.values_list("status", flat=True)) == {"completed"}
    total = turns.aggregate(c=Sum("cost"))["c"]
    assert (
        project.spent
        == total
        == LLMCall.objects.filter(project=project).aggregate(c=Sum("cost"))["c"]
    )
    phase_costs = [Decimal(e.payload["cost"]) for e in events(project, "phase.completed")]
    assert sum(phase_costs) == total
    assert all(c > 0 for c in phase_costs)
    task_costs = [Decimal(e.payload["cost"]) for e in events(project, "task.completed")]
    assert len(task_costs) == 2
    assert all(c > 0 for c in task_costs)
    completed = events(project, "project.completed")[0].payload
    assert Decimal(completed["cost"]) == total

    costs = client.get(f"/api/v1/projects/{project.id}/costs").json()
    assert Decimal(costs["spent"]) == total
    assert sum(Decimal(p["cost"]) for p in costs["by_phase"]) == total
    assert {a["role"] for a in costs["by_agent"]} >= {"analyst", "developer"}
    assert len(costs["by_task"]) == 2
    assert costs["by_provider"][0]["provider"] == "fake"
    assert costs["estimate"]["basis"] == "static"


def test_refused_call_mid_turn_resumes_the_same_turn(client, settings, monkeypatch):
    """The budget runs out between two LLM calls of one turn: the turn stays `running`, the
    step goes back to the queue with its attempt refunded, and the resumed turn reuses the
    calls already paid."""
    from dexterhouse.apps.observability.services import budget
    from dexterhouse.apps.projects.models import Project

    project = create(client, execution_mode="autonomous", budget="20")
    original = budget.check_before_call
    seen = {"n": 0}

    def squeeze(organization_id, project_id):
        seen["n"] += 1
        if seen["n"] == 2:  # second call of the first turn
            spent = Project.objects.get(pk=project_id).spent
            Project.objects.filter(pk=project_id).update(budget=spent)
        return original(organization_id, project_id)

    monkeypatch.setattr(budget, "check_before_call", squeeze)
    client.post(f"/api/v1/projects/{project.id}/start")
    drain(project)

    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "budget")
    turn = AgentTurn.objects.get(project=project)
    assert turn.status == "running"
    step = StepRun.objects.get(project=project, status="queued")
    assert (step.attempts, step.error.split(":")[0]) == (0, "budget")
    paid = LLMCall.objects.filter(project=project).count()

    client.patch(f"/api/v1/projects/{project.id}", {"budget": "20"}, format="json")
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed", event_types(project)[-5:]
    turn.refresh_from_db()
    assert turn.status == "completed"  # the same turn finished, no second turn for the step
    assert AgentTurn.objects.filter(step_run=step).count() == 1
    assert LLMCall.objects.filter(agent_turn=turn).count() >= paid
