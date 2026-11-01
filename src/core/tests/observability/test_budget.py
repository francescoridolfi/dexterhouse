# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget thresholds, pre-call refusal, raising the budget (F-012, flow F7)."""

from decimal import Decimal

import pytest

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.gateway.messages import CompletionRequest, Message, TextPart, Usage
from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.gateway.providers import FakeProvider
from dexterhouse.apps.gateway.providers.fake import FakeResponse
from dexterhouse.apps.gateway.services.complete import complete
from dexterhouse.apps.observability.services import budget
from dexterhouse.apps.observability.services.budget import BudgetExceededError
from dexterhouse.apps.projects.services import lifecycle
from dexterhouse.apps.workflows.models import Gate, GateStatus
from dexterhouse.common.errors import BudgetExhaustedError
from tests.workflows.conftest import drain

pytestmark = pytest.mark.django_db


def types(project, prefix=""):
    rows = Event.objects.filter(project_id=project.id, type__startswith=prefix)
    return [e.type for e in rows.order_by("created_at", "id")]


def payload(project, event_type):
    return Event.objects.filter(project_id=project.id, type=event_type).latest("created_at").payload


@pytest.fixture
def running(started):
    """A running supervised project waiting at its first gate, budget 1 EUR."""
    project = started(budget="1")
    drain(project)
    project.refresh_from_db()
    return project


def request():
    return CompletionRequest(
        messages=[Message(role="user", parts=[TextPart(text="hi")])],
        profile="fast",
        model="fake-model",
        max_tokens=10,
    )


def test_record_spend_sums_calls_and_unpriced_tokens(project, make_call, organization):
    make_call(project, "0.25")
    make_call(project, None, input_tokens=7, output_tokens=3)
    make_call(project, "9", status="error")  # failed calls never count
    budget.record_spend(organization.id, project.id)
    project.refresh_from_db()
    organization.refresh_from_db()
    assert project.spent == Decimal("0.25")
    assert project.spent_unpriced_tokens == 10
    assert organization.spent_month == Decimal("0.25")
    budget.record_spend(organization.id, project.id)  # idempotent
    project.refresh_from_db()
    assert project.spent == Decimal("0.25")


def test_warning_at_80_then_exceeded_opens_budget_gate(running, make_call, organization):
    project = running
    make_call(project, "0.5")
    budget.record_spend(organization.id, project.id)
    assert "budget.warning" not in types(project, "budget.")
    make_call(project, "0.3")
    budget.record_spend(organization.id, project.id)
    assert payload(project, "budget.warning") == {
        "spent": "0.800000",
        "budget": "1.000000",
        "pct": 80,
    }
    make_call(project, "0.3")
    budget.record_spend(organization.id, project.id)
    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "budget")
    gate = Gate.objects.get(project=project, gate_id="budget")
    assert (gate.type, gate.status, gate.payload["reason"]) == ("escalation", "open", "budget")
    exceeded = payload(project, "budget.exceeded")
    assert exceeded["gate_id"] == str(gate.id)
    assert types(project, "budget.").count("budget.warning") == 1
    waiting = payload(project, "project.waiting")
    assert waiting == {"reason": "budget", "gate_id": str(gate.id)}
    # A second crossing does not open a second gate.
    budget.on_budget_exhausted(project)
    assert Gate.objects.filter(project=project, gate_id="budget").count() == 1


def test_complete_refuses_when_exhausted_and_records_spend(running, organization):
    project = running
    provider = FakeProvider([FakeResponse(text="ok", usage=Usage(input=10, output=10))])
    complete(request(), provider=provider, organization_id=organization.id, project_id=project.id)
    project.refresh_from_db()
    assert project.spent > 0
    project.budget = project.spent
    project.save(update_fields=["budget"])
    with pytest.raises(BudgetExceededError) as info:
        complete(
            request(), provider=provider, organization_id=organization.id, project_id=project.id
        )
    assert (info.value.code, info.value.retryable, info.value.scope) == ("budget", False, "project")
    assert LLMCall.objects.filter(project=project).count() == 1
    project.refresh_from_db()
    assert project.waiting_reason == "budget"
    assert Gate.objects.filter(project=project, gate_id="budget", status="open").exists()


def test_org_budget_refuses_and_resumes_when_raised(running, organization, make_call):
    project = running
    organization.budget_monthly = Decimal("0.1")
    organization.save()
    make_call(project, "0.2")
    budget.record_spend(organization.id, project.id)
    assert "budget.org_exceeded" in types(project, "budget.")
    with pytest.raises(BudgetExceededError) as info:
        budget.check_before_call(organization.id, project.id)
    assert info.value.scope == "organization"
    project.refresh_from_db()
    assert project.waiting_reason == "budget"
    assert not Gate.objects.filter(project=project, gate_id="budget").exists()
    with pytest.raises(BudgetExhaustedError):
        budget.ensure_org_can_start(organization)
    organization.refresh_from_db()
    organization.budget_monthly = Decimal("10")
    organization.save()
    assert budget.on_org_budget_changed(organization) == [project.id]
    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "gate")  # first gate still open


def test_org_warning(running, organization, make_call):
    organization.budget_monthly = Decimal("1")
    organization.save()
    make_call(running, "0.85")
    budget.record_spend(organization.id, running.id)
    assert types(running, "budget.") == ["budget.estimated", "budget.warning", "budget.org_warning"]


def test_raising_project_budget_closes_gate_and_resumes(client, running, make_call, organization):
    project = running
    make_call(project, "2")
    budget.record_spend(organization.id, project.id)
    gate = Gate.objects.get(project=project, gate_id="budget")
    response = client.patch(f"/api/v1/projects/{project.id}", {"budget": "1.5"}, format="json")
    assert response.status_code == 200
    gate.refresh_from_db()
    assert gate.status == "open"  # still under water
    response = client.patch(f"/api/v1/projects/{project.id}", {"budget": "5"}, format="json")
    gate.refresh_from_db()
    assert (gate.status, gate.decision) == (GateStatus.APPROVED, "retry")
    decided = payload(project, "gate.decided")
    assert decided["next"] == "project_resumed"
    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "gate")
    assert "project.resumed" in types(project, "project.")


def test_decide_budget_gate_retry_needs_budget_then_drop(client, running, make_call, organization):
    project = running
    make_call(project, "2")
    budget.record_spend(organization.id, project.id)
    gate = Gate.objects.get(project=project, gate_id="budget")
    url = f"/api/v1/gates/{gate.id}/decide"
    response = client.post(url, {"decision": "retry"}, format="json")
    assert response.status_code == 402
    assert response.json()["type"].endswith("/budget-exceeded")
    assert client.post(url, {"decision": "accept"}, format="json").status_code == 400
    response = client.post(url, {"decision": "drop", "comment": "too expensive"}, format="json")
    assert response.status_code == 200
    assert response.json()["next"] == "phase_failed"
    project.refresh_from_db()
    assert project.status == "failed"
    assert client.post(url, {"decision": "drop"}, format="json").status_code == 409


def test_decide_budget_gate_retry_after_raise(client, running, make_call, organization):
    project = running
    make_call(project, "2")
    budget.record_spend(organization.id, project.id)
    gate = Gate.objects.get(project=project, gate_id="budget")
    project.budget = Decimal(3)  # raised outside the API (no hook)
    project.save(update_fields=["budget"])
    response = client.post(f"/api/v1/gates/{gate.id}/decide", {"decision": "retry"}, format="json")
    assert response.status_code == 200
    assert response.json()["next"] == "project_resumed"


def test_resume_and_start_answer_402(client, running, make_call, organization, user, make_project):
    project = running
    lifecycle.pause_project(project.id, user)
    make_call(project, "2")
    budget.record_spend(organization.id, project.id)
    project.refresh_from_db()
    assert project.status == "paused"  # a paused project stays paused
    response = client.post(f"/api/v1/projects/{project.id}/resume")
    assert response.status_code == 402
    organization.refresh_from_db()
    organization.budget_monthly = Decimal("1")
    organization.save()
    draft = make_project(name="Other")
    response = client.post(f"/api/v1/projects/{draft.id}/start")
    assert response.status_code == 402


def test_budget_without_process_run_only_waits(project, make_call, organization):
    # A draft project has no phase: nothing to open a gate on, nothing to pause.
    make_call(project, "10")
    budget.record_spend(organization.id, project.id)
    project.refresh_from_db()
    assert project.status == "draft"
    assert not Gate.objects.filter(project=project).exists()
