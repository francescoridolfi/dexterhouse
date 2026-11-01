# SPDX-License-Identifier: AGPL-3.0-or-later
"""Done criterion of the integration: `software-house-default` end to end via the API with
the real `AgentsTurnRunner`, the gateway's `fake` provider and one test package per role."""

from collections import Counter

import pytest

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn, ToolCall
from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.memory.models import MemoryChunk
from dexterhouse.apps.projects.models import Artifact
from dexterhouse.apps.workflows.models import Gate, StepRun, StepRunStatus, Task
from tests.workflows.conftest import drain, event_types, events, open_gate
from tests.workflows.test_e2e import create, decide

pytestmark = [
    pytest.mark.slow,  # starts a stdio MCP server process per turn, dozens of turns
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("real_runtime"),
]


def assert_turns_are_real(project) -> None:
    """One completed AgentTurn per step run; artifacts stored by turns, indexed, in events."""
    steps = StepRun.objects.filter(project=project)
    assert set(steps.values_list("status", flat=True)) == {StepRunStatus.COMPLETED}
    assert not steps.filter(agent_turn__isnull=True).exists()
    turns = AgentTurn.objects.filter(project=project)
    assert set(turns.values_list("status", flat=True)) == {"completed"}
    assert Counter(turns.values_list("step_run_id", flat=True)).most_common(1)[0][1] == 1
    assert turns.count() == steps.count()
    for step in steps.select_related("agent", "agent_turn"):
        assert step.agent_turn.agent_instance_id == step.agent_id
        assert step.agent.role == step.role
        assert step.agent.package_path
    produced = Artifact.objects.filter(project=project).exclude(kind="brief")
    assert not produced.filter(produced_by_turn__isnull=True).exists()
    completed = events(project, "agent.turn.completed")
    assert len(completed) == turns.count()
    refs = {a["id"] for e in completed for a in e.payload["artifacts"]}
    assert refs == {str(i) for i in produced.values_list("id", flat=True)}
    indexed = set(MemoryChunk.objects.filter(project=project).values_list("artifact_id", flat=True))
    assert set(produced.values_list("id", flat=True)) <= indexed
    calls = LLMCall.objects.filter(project=project)
    assert calls.exists()
    assert not calls.filter(agent_turn__isnull=True).exists()
    assert set(calls.values_list("status", flat=True)) == {"ok"}


def test_supervised_end_to_end_with_real_turns(client):
    project = create(client, execution_mode="supervised")
    assert client.post(f"/api/v1/projects/{project.id}/start").status_code == 200
    team = AgentInstance.objects.filter(project=project)
    assert team.count() == 7
    drain(project)

    gate = open_gate(project)
    assert (gate.type, gate.gate_id) == ("question", "question")
    ask = ToolCall.objects.get(agent_turn__project=project, tool="project.ask")
    assert ask.status == "done"
    assert '"mode": "ask"' in ask.result["content"]
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
    requirements = Artifact.objects.get(project=project, kind="requirements")
    assert "Answers: No; No" in requirements.content
    assert requirements.produced_by_turn.step_run.role == "analyst"
    loaded = [e.payload["skill"] for e in events(project, "agent.skill.loaded")]
    assert {"brief-reading", "small-steps"} <= set(loaded)
    tools = set(ToolCall.objects.filter(agent_turn__project=project).values_list("tool", flat=True))
    assert {"project.ask", "skills.read", "project.tasks", "memory.search"} <= tools
    assert not ToolCall.objects.filter(agent_turn__project=project).exclude(status="done").exists()


def test_autonomous_end_to_end_with_real_turns(client, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"tasks": 2, "hire": True}
    project = create(client, execution_mode="autonomous")
    client.post(f"/api/v1/projects/{project.id}/start")
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed", event_types(project)[-5:]
    assert set(Gate.objects.filter(project=project).values_list("status", flat=True)) == {
        "auto_approved"
    }
    assert not ToolCall.objects.filter(agent_turn__project=project, tool="project.ask").exists()
    assert Artifact.objects.filter(project=project, kind="assumptions").exists()
    assert_turns_are_real(project)
    hired = AgentInstance.objects.get(project=project, role="htmx_frontend_developer")
    assert hired.allowed_tools == []  # the proposal granted no permission
    replan = StepRun.objects.get(project=project, step="replan")
    assert replan.agent_turn.output["artifacts"][0]["kind"] == "task_board"
