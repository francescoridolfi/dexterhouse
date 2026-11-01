# SPDX-License-Identifier: AGPL-3.0-or-later
"""Done criterion of E-02: the built-in processes run end to end via the API, fake agents."""

import pytest

from dexterhouse.apps.projects.models import Artifact, Project
from dexterhouse.apps.workflows.models import (
    Gate,
    PhaseRun,
    ProcessRun,
    StepRun,
    StepRunStatus,
    Task,
)
from tests.workflows.conftest import BRIEF, drain, event_types, events, open_gate

pytestmark = pytest.mark.django_db
FAMILIES = ("project.", "process.", "phase.", "task.", "gate.")


def create(client, **extra):
    body = {"name": "GymBook", "brief": BRIEF, "budget": 20, **extra}
    response = client.post("/api/v1/projects", body, format="json")
    assert response.status_code == 201, response.json()
    return Project.objects.get(pk=response.json()["id"])


def decide(client, gate: Gate, **body):
    response = client.post(f"/api/v1/gates/{gate.id}/decide", body, format="json")
    assert response.status_code == 200, response.json()
    return response.json()


def test_supervised_software_house_default_end_to_end(client):
    project = create(client, execution_mode="supervised")
    assert client.post(f"/api/v1/projects/{project.id}/start").status_code == 200
    drain(project)

    gate = open_gate(project)
    assert (gate.type, gate.gate_id) == ("question", "question")
    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "gate")
    answers = [{"question_id": q["id"], "answer": "No"} for q in gate.payload["questions"]]
    assert decide(client, gate, answers=answers)["next"] == "phase_resumed"

    approvals = []
    for _ in range(20):
        drain(project)
        gate = open_gate(project)
        if gate is None:
            break
        assert gate.type == "approval"
        approvals.append(gate.gate_id)
        assert decide(client, gate, decision="approve")["next"] == "phase_completed"

    project.refresh_from_db()
    assert project.status == "completed"
    assert approvals == [
        "approve_requirements",
        "approve_architecture",
        "approve_plan",
        "approve_release",
    ]
    assert set(PhaseRun.objects.values_list("status", flat=True)) == {"completed"}
    assert ProcessRun.objects.get(project=project).status == "completed"
    assert Task.objects.filter(project=project, status="done").count() == 3
    assert not StepRun.objects.exclude(status=StepRunStatus.COMPLETED).exists()

    types = event_types(project)
    for family in FAMILIES:
        assert any(t.startswith(family) for t in types), family
    for expected in (
        "project.created",
        "project.started",
        "project.waiting",
        "project.resumed",
        "project.completed",
        "process.started",
        "process.completed",
        "phase.ready",
        "phase.started",
        "phase.step.completed",
        "phase.exit_checked",
        "phase.completed",
        "task.created",
        "task.ready",
        "task.started",
        "task.step.completed",
        "task.completed",
        "gate.opened",
        "gate.decided",
        "question.answered",
        "workspace.created",
        "branch.merged",
    ):
        assert expected in types, expected
    decided = [e.payload for e in events(project, "gate.decided")]
    assert all(d["auto"] is False and d["decided_by"]["name"] == "ada" for d in decided)
    answered = Artifact.objects.get(project=project, kind="requirements")
    assert "Answers: No; No" in answered.content
    assert project.stack["language"] == "python"


def test_autonomous_software_house_default_auto_approves_and_never_asks(client):
    project = create(client, execution_mode="autonomous")
    client.post(f"/api/v1/projects/{project.id}/start")
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"
    assert not Gate.objects.filter(project=project, type="question").exists()
    statuses = set(Gate.objects.filter(project=project).values_list("status", flat=True))
    assert statuses == {"auto_approved"}
    decided = [e.payload for e in events(project, "gate.decided")]
    assert len(decided) == 4
    assert all(d["auto"] and d["decided_by"] is None for d in decided)
    assert "project.waiting" not in event_types(project)
    assert Artifact.objects.filter(project=project, kind="assumptions").exists()


def test_autonomous_always_required_gate_still_blocks(client):
    project = create(
        client,
        execution_mode="autonomous",
        gate_overrides={"approve_release": "always_required"},
    )
    client.post(f"/api/v1/projects/{project.id}/start")
    drain(project)
    gate = open_gate(project)
    assert gate.gate_id == "approve_release"
    decide(client, gate, decision="approve")
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"


STACK = {
    "language": "python",
    "framework": "django",
    "workspace_image": "dexterhouse/workspace:python",
    "package_manager": "uv",
    "test_command": "uv run pytest -q",
    "run_command": "uv run manage.py runserver",
}


@pytest.mark.parametrize("mode", ["supervised", "autonomous"])
def test_code_review_only_runs(client, mode):
    project = create(client, process="code-review-only", execution_mode=mode, stack=STACK)
    assert client.post(f"/api/v1/projects/{project.id}/start").status_code == 200
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"
    assert Artifact.objects.filter(project=project, kind="review").count() == 1
    gate = Gate.objects.get(project=project)
    assert (gate.gate_id, gate.status) == ("approve_review", "auto_approved")
    assert "workspace.requested" in event_types(project)


def test_code_review_only_requires_stack(client):
    project = create(client, process="code-review-only")
    response = client.post(f"/api/v1/projects/{project.id}/start")
    assert response.status_code == 400
    body = response.json()
    assert response["Content-Type"] == "application/problem+json"
    assert body["type"].endswith("/validation-error")
    assert body["errors"][0]["field"] == "stack"
