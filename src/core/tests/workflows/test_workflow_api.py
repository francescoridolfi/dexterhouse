# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1 phases, tasks, gates."""

import pytest
from rest_framework.test import APIClient

from dexterhouse.apps.accounts.services.tokens import create_token
from dexterhouse.apps.workflows.models import Task
from tests.workflows.conftest import drain, open_gate

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def script(settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "tasks": 2}


@pytest.fixture
def project(started):
    project = started(gate_overrides={})
    drain(project)
    return project


def test_phases_list_detail_and_skip(client, project, make_member):
    phases = client.get(f"/api/v1/projects/{project.id}/phases").json()["results"]
    analysis = phases[0]
    assert (analysis["phase_id"], analysis["status"]) == ("analysis", "waiting_gate")
    assert analysis["gate"]["gate_id"] == "approve_requirements"
    assert analysis["agents"][0]["role"] == "analyst"
    detail = client.get(f"/api/v1/phases/{analysis['id']}").json()
    assert detail["turns"][0]["status"] == "completed"
    assert {a["kind"] for a in detail["artifacts"]} == {"requirements", "user_stories"}
    retro = phases[-1]
    assert make_member("member").post(f"/api/v1/phases/{retro['id']}/skip").status_code == 403
    assert client.post(f"/api/v1/phases/{retro['id']}/skip").json()["status"] == "skipped"
    again = client.post(f"/api/v1/phases/{retro['id']}/skip")
    assert again.status_code == 409
    assert again.json()["type"] == "https://dexterhouse.dev/errors/invalid-transition"


def test_gate_inbox_detail_and_decide_permissions(
    client, project, make_member, organization, django_user_model
):
    inbox = client.get("/api/v1/gates?status=open").json()["results"]
    assert len(inbox) == 1
    gate_id = inbox[0]["id"]
    detail = client.get(f"/api/v1/gates/{gate_id}").json()
    assert {a["kind"] for a in detail["artifacts"]} == {"requirements", "user_stories"}
    assert detail["artifacts"][0]["content"].startswith("# ")
    url = f"/api/v1/gates/{gate_id}/decide"
    assert make_member("member").post(url, {"decision": "approve"}).status_code == 403
    viewer = make_member("viewer")
    assert viewer.post(url, {"decision": "approve"}).status_code == 403
    admin = make_member("admin", "marta")
    assert admin.post(url, {"decision": "bogus"}).status_code == 400
    _, token = create_token(
        organization=organization,
        user=django_user_model.objects.get(username="marta"),
        name="t",
        scopes=["projects:read"],
    )
    bearer = APIClient()
    bearer.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert bearer.post(url, {"decision": "approve"}).status_code == 403
    decided = admin.post(url, {"decision": "approve", "comment": "ok, FIFO"}, format="json")
    assert decided.json()["next"] == "phase_completed"
    assert decided.json()["decided_by"]["name"] == "marta"
    twice = admin.post(url, {"decision": "approve"})
    assert twice.status_code == 409
    assert "already decided by marta" in twice.json()["detail"]
    history = client.get(f"/api/v1/projects/{project.id}/gates").json()["results"]
    assert history[0]["status"] == "approved"


def approve_all_until_loop(client, project):
    for _ in range(3):
        gate = open_gate(project)
        client.post(f"/api/v1/gates/{gate.id}/decide", {"decision": "approve"})
        drain(project)


def test_tasks_list_detail_patch_cancel_and_create(client, project):
    approve_all_until_loop(client, project)
    url = f"/api/v1/projects/{project.id}/tasks"
    tasks = client.get(url).json()["results"]
    assert [t["external_id"] for t in tasks] == ["T-01", "T-02"]
    assert {t["status"] for t in tasks} == {"done"}
    done = tasks[0]
    detail = client.get(f"/api/v1/tasks/{done['id']}").json()
    assert [s["step"] for s in detail["turns"]] == ["developer", "reviewer", "tester"]
    assert client.patch(f"/api/v1/tasks/{done['id']}", {"title": "x"}).status_code == 409
    assert client.post(f"/api/v1/tasks/{done['id']}/cancel").status_code == 409
    assert client.get(f"{url}?status=done&kind=feature").json()["results"]
    late = client.post(url, {"title": "Late", "acceptance": ["works"]}, format="json")
    assert late.status_code == 409  # implementation is over


def test_add_edit_and_cancel_tasks_during_implementation(client, started, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "tasks": 2, "delay_s": 0}
    project = started(gate_overrides={})
    drain(project)
    approve_all_until_loop_partially(client, project)
    url = f"/api/v1/projects/{project.id}/tasks"
    first = Task.objects.get(project=project, external_id="T-01")
    added = client.post(
        url,
        {"title": "Docs", "acceptance": ["README"], "depends_on": [str(first.id)]},
        format="json",
    )
    assert added.status_code == 201, added.json()
    assert added.json()["external_id"] == "T-03"
    bad = client.post(url, {"title": "x", "acceptance": ["y"], "depends_on": [str(project.id)]})
    assert bad.status_code == 400
    third = added.json()["id"]
    patched = client.patch(f"/api/v1/tasks/{third}", {"title": "Docs v2"}, format="json")
    assert patched.json()["title"] == "Docs v2"
    assert client.patch(f"/api/v1/tasks/{third}", {"estimate": "L"}).status_code == 400
    assert client.post(f"/api/v1/tasks/{third}/cancel").json()["status"] == "cancelled"
    drain(project)
    gate = open_gate(project)
    assert gate.gate_id == "approve_release"


def approve_all_until_loop_partially(client, project):
    """Approve analysis and architecture, then approve the plan without draining."""
    for _ in range(2):
        gate = open_gate(project)
        client.post(f"/api/v1/gates/{gate.id}/decide", {"decision": "approve"})
        drain(project)
    gate = open_gate(project)
    client.post(f"/api/v1/gates/{gate.id}/decide", {"decision": "approve"})
