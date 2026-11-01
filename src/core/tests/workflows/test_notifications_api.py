# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1 notifications and the gate inbox (E-06)."""

import pytest

from dexterhouse.apps.notifications.models import Notification
from tests.workflows.conftest import drain, open_gate

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def script(settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"tasks": 1}


@pytest.fixture
def admin(make_member):
    return make_member("admin", "marta")


@pytest.fixture
def asking(started, admin):
    """A supervised project waiting on the analyst's question gate (deciders: ada, marta)."""
    project = started()
    drain(project)
    return project


def test_unread_list_count_and_marking(client, asking, admin):
    gate = open_gate(asking)
    assert gate.type == "question"
    assert client.get("/api/v1/notifications/unread_count").json() == {"count": 1}
    rows = client.get("/api/v1/notifications?unread=true").json()["results"]
    assert len(rows) == 1
    row = rows[0]
    assert (row["kind"], row["gate"], row["read"]) == ("gate_opened", str(gate.id), False)
    assert row["data"]["gate_type"] == "question"
    assert row["data"]["phase_id"] == "analysis"
    assert client.get(f"/api/v1/notifications?project={asking.id}").json()["results"]
    other = Notification.objects.get(user__username="marta")
    assert client.post(f"/api/v1/notifications/{other.id}/read").status_code == 404
    read = client.post(f"/api/v1/notifications/{row['id']}/read").json()
    assert read["read"] is True
    assert client.get("/api/v1/notifications/unread_count").json() == {"count": 0}
    assert admin.post("/api/v1/notifications/read", {}, format="json").json() == {"marked": 1}
    assert admin.get("/api/v1/notifications?unread=1").json()["results"] == []


def test_mark_selected_ids(client, asking):
    note = Notification.objects.get(user__username="ada")
    body = {"ids": [str(note.id)]}
    assert client.post("/api/v1/notifications/read", body, format="json").json() == {"marked": 1}


def test_members_answer_questions_but_only_admins_approve(asking, make_member, client):
    gate = open_gate(asking)
    url = f"/api/v1/gates/{gate.id}/decide"
    answers = [{"question_id": q["id"], "answer": "yes"} for q in gate.payload["questions"]]
    viewer = make_member("viewer")
    assert viewer.post(url, {"answers": answers}, format="json").status_code == 403
    member = make_member("member")
    response = member.post(url, {"answers": answers}, format="json")
    assert response.status_code == 200, response.json()
    assert response.json()["next"] == "phase_resumed"
    assert (response.json()["status"], response.json()["decided_by"]["name"]) == (
        "answered",
        "member",
    )
    drain(asking)
    approval = open_gate(asking)
    approve = f"/api/v1/gates/{approval.id}/decide"
    assert member.post(approve, {"decision": "approve"}).status_code == 403


def test_inbox_filters_and_gate_fields(client, asking, started):
    other = started(name="Other")
    drain(other)
    rows = client.get("/api/v1/gates?status=open&type=question").json()["results"]
    assert len(rows) == 2
    one = client.get(f"/api/v1/gates?status=open&project={asking.id}").json()["results"]
    assert [r["project"] for r in one] == [str(asking.id)]
    gate = one[0]
    assert gate["project_name"] == "GymBook"
    assert gate["phase_id"] == "analysis"
    assert gate["title"].endswith("from the analyst")
    assert gate["reminders"] == 0
    assert gate["notified_at"] is not None
    assert client.get("/api/v1/gates?type=approval&status=open").json()["results"] == []
