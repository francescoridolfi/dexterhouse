# SPDX-License-Identifier: AGPL-3.0-or-later
"""Done criterion of E-04: the built-in processes end to end via the API with the real
`AgentsTurnRunner`, the built-in agent packages and the demo responder (no LLM)."""

import importlib

import pytest

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn, ToolCall
from dexterhouse.apps.projects.models import Artifact
from dexterhouse.apps.workflows.models import Gate, StepRun, Task
from tests.brief_samples import structure
from tests.conftest import TEAM_PACKAGES, install_test_packages
from tests.workflows.conftest import drain, event_types, events, open_gate
from tests.workflows.test_e2e import STACK, create, decide
from tests.workflows.test_e2e_agents import assert_turns_are_real

pytestmark = [
    pytest.mark.slow,  # whole process runs with the built-in agents, one MCP process per turn
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("builtin_runtime"),
]


def test_agents_turn_runner_is_the_default():
    base = importlib.import_module("dexterhouse.settings.base")
    assert base.WORKFLOWS_TURN_RUNNER.endswith("runners.agents.AgentsTurnRunner")


def test_supervised_software_house_default_with_builtin_agents(client):
    project = create(client, execution_mode="supervised")
    assert client.post(f"/api/v1/projects/{project.id}/start").status_code == 200
    team = AgentInstance.objects.filter(project=project)
    assert {a.source for a in team} == {"builtin"}
    assert all(a.package_path for a in team)
    drain(project)

    gate = open_gate(project)
    assert (gate.type, gate.gate_id) == ("question", "question")
    ask = ToolCall.objects.get(agent_turn__project=project, tool="project.ask")
    assert '"mode": "ask"' in ask.result["content"]
    draft = Artifact.objects.get(project=project, kind="requirements", version=1)
    assert draft.content.startswith("> DRAFT pending answers")
    answers = [{"question_id": q["id"], "answer": "No"} for q in gate.payload["questions"]]
    decide(client, gate, answers=answers)

    approvals = []
    for _ in range(20):
        drain(project)
        gate = open_gate(project)
        if gate is None:
            break
        approvals.append(gate.gate_id)
        decide(client, gate, decision="approve")

    project.refresh_from_db()
    assert project.status == "completed", event_types(project)[-5:]
    assert approvals == [
        "approve_requirements",
        "approve_architecture",
        "approve_plan",
        "approve_release",
    ]
    assert Task.objects.filter(project=project, status="done").count() == 3
    assert_turns_are_real(project)
    final = Artifact.objects.filter(project=project, kind="requirements").latest("version")
    assert "DRAFT" not in final.content
    assert not Artifact.objects.filter(project=project, kind="assumptions").exists()
    loaded = {e.payload["skill"] for e in events(project, "agent.skill.loaded")}
    assert {"requirements-elicitation", "architecture-decision", "review-checklist"} <= loaded
    developer = AgentTurn.objects.filter(project=project, agent_instance__role="developer").first()
    # installed (E-05) but no runner in this test: the workspace tools are left out of the turn
    assert (
        developer.context_manifest["unavailable_tools"]["workspace.write"] == "workspace_not_ready"
    )
    assert not ToolCall.objects.filter(agent_turn__project=project, status="denied").exists()
    structure.assert_artifacts_are_well_formed(project)
    structure.assert_analysis(project)
    structure.assert_delivery(project)


def test_autonomous_software_house_default_with_review_rounds_and_a_hire(client, settings):
    settings.AGENTS_DEMO_SCRIPT = {
        "tasks": 3,
        "hire": True,
        "verdicts": {"reviewer:T-02": ["request_changes", "request_changes", "approve"]},
    }
    install_test_packages(TEAM_PACKAGES)  # extra roles; the built-in team stays
    project = create(client, execution_mode="autonomous")
    client.post(f"/api/v1/projects/{project.id}/start")
    drain(project)

    project.refresh_from_db()
    assert project.status == "completed", event_types(project)[-5:]
    assert set(Gate.objects.filter(project=project).values_list("status", flat=True)) == {
        "auto_approved"
    }
    ask = ToolCall.objects.get(agent_turn__project=project, tool="project.ask")
    assert '"mode": "assume"' in ask.result["content"]
    assert Artifact.objects.filter(project=project, kind="assumptions").exists()
    assert not Artifact.objects.filter(project=project, kind="questions").exists()
    assert_turns_are_real(project)
    hired = AgentInstance.objects.get(project=project, role="htmx_frontend_developer")
    assert hired.allowed_tools == ["project.tasks"]
    replan = StepRun.objects.get(project=project, step="replan")
    board = replan.agent_turn.output["artifacts"][0]["data"]
    assert board["tasks"][-1]["assigned_role"] == "htmx_frontend_developer"
    reviews = Artifact.objects.filter(project=project, kind="review", name__contains="T-02")
    assert reviews.count() == 3
    last = reviews.get(name="reviews/T-02-iter3.md").data
    assert [f["id"] for f in last["findings"]] == ["R-1", "R-2"]
    assert all(f["resolved"] for f in last["findings"])
    structure.assert_artifacts_are_well_formed(project)
    structure.assert_planning(
        project, {"developer", "htmx_frontend_developer", "reviewer", "tester"}
    )
    structure.assert_delivery(project)


@pytest.mark.parametrize("mode", ["supervised", "autonomous"])
def test_code_review_only_with_the_builtin_reviewer(client, mode):
    project = create(client, process="code-review-only", execution_mode=mode, stack=STACK)
    assert client.post(f"/api/v1/projects/{project.id}/start").status_code == 200
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed", event_types(project)[-5:]
    (review,) = Artifact.objects.filter(project=project, kind="review")
    assert review.name == "reviews/repository-iter1.md"
    assert review.data["findings"][0]["id"] == "R-1"
    assert review.produced_by_turn.agent_instance.package_name == "reviewer"
    assert review.produced_by_turn.output["verdict"] == review.data["verdict"]
    stack = Artifact.objects.get(project=project, kind="stack")
    assert stack.produced_by_turn is None  # given with the project, not by an agent
    structure.assert_artifacts_are_well_formed(project)
    structure.assert_reviews(project)
