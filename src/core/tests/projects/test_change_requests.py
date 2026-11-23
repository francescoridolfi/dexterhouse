# SPDX-License-Identifier: AGPL-3.0-or-later
"""Change requests (docs/specs/change-requests.md): numbering, states, roles, API."""

import pytest

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import ChangeRequest, Project

pytestmark = pytest.mark.django_db
BODY = {"title": "Add a waiting list", "body": "Members join a waiting list.", "budget": "3"}


def create(api, project: Project, **extra):
    url = f"/api/v1/projects/{project.id}/change-requests"
    return api.post(url, {**BODY, **extra}, format="json")


def created(api, project: Project, **extra) -> dict:
    response = create(api, project, **extra)
    assert response.status_code == 201, response.json()
    return response.json()


def types(project: Project) -> list[str]:
    rows = Event.objects.filter(project_id=project.id, type__startswith="change_request.")
    return list(rows.order_by("created_at", "id").values_list("type", flat=True))


def test_member_creates_numbered_drafts(project, make_member):
    member = make_member("member")
    first, second = created(member, project), created(member, project, title="Export CSV")
    assert (first["number"], first["label"], first["status"]) == (1, "CR-1", "draft")
    assert (second["number"], second["label"]) == (2, "CR-2")
    assert first["budget"] == "3.000000"
    assert first["created_by"] == "member"
    assert types(project) == ["change_request.created"] * 2
    listed = member.get(f"/api/v1/projects/{project.id}/change-requests").json()["results"]
    assert [r["number"] for r in listed] == [1, 2]


def test_viewer_reads_but_cannot_create(project, make_member, client):
    cr = created(client, project)
    viewer = make_member("viewer")
    assert viewer.get(f"/api/v1/change-requests/{cr['id']}").json()["title"] == BODY["title"]
    assert create(viewer, project).status_code == 403


@pytest.mark.parametrize(
    ("extra", "field"),
    [({"title": "x" * 121}, "title"), ({"body": "x" * 20_001}, "body"), ({"budget": -1}, "budget")],
)
def test_validation(project, client, extra, field):
    response = create(client, project, **extra)
    assert response.status_code == 400
    assert field in {e["field"] for e in response.json()["errors"]}


def test_only_drafts_are_editable(project, client):
    cr = created(client, project)
    url = f"/api/v1/change-requests/{cr['id']}"
    response = client.patch(url, {"title": "Waiting list v2"}, format="json")
    assert response.status_code == 200
    assert response.json()["title"] == "Waiting list v2"
    assert client.post(f"{url}/queue").json()["status"] == "queued"
    response = client.patch(url, {"title": "late"}, format="json")
    assert response.status_code == 409
    assert response.json()["type"].endswith("invalid-transition")
    assert types(project)[-2:] == ["change_request.updated", "change_request.queued"]


def test_member_cannot_queue_or_cancel(project, make_member):
    member = make_member("member")
    cr = created(member, project)
    assert member.post(f"/api/v1/change-requests/{cr['id']}/queue").status_code == 403
    assert member.post(f"/api/v1/change-requests/{cr['id']}/cancel").status_code == 403


def test_queued_on_an_active_project_waits(started, client):
    project = started()
    cr = created(client, project)
    assert client.post(f"/api/v1/change-requests/{cr['id']}/queue").json()["status"] == "queued"
    project.refresh_from_db()
    assert project.status != "completed"
    assert ChangeRequest.objects.get(pk=cr["id"]).process_run is None


def test_cancel_from_draft_or_queued_only(project, client):
    draft, queued = created(client, project), created(client, project)
    client.post(f"/api/v1/change-requests/{queued['id']}/queue")
    for cr in (draft, queued):
        response = client.post(f"/api/v1/change-requests/{cr['id']}/cancel")
        assert response.json()["status"] == "cancelled"
    again = client.post(f"/api/v1/change-requests/{draft['id']}/cancel")
    assert again.status_code == 409
    assert client.post(f"/api/v1/change-requests/{draft['id']}/queue").status_code == 409


def test_archived_project_refuses_new_change_requests(project, client):
    assert client.delete(f"/api/v1/projects/{project.id}").status_code == 204
    response = create(client, project)
    assert response.status_code == 409


def test_estimate(project, make_member):
    member = make_member("member")
    cr = created(member, project)
    data = member.get(f"/api/v1/change-requests/{cr['id']}/estimate").json()
    assert data["currency"] == "EUR"
    assert data["low"] <= data["high"]
    assert make_member("viewer", "v2").get(
        f"/api/v1/change-requests/{cr['id']}/estimate"
    ).status_code == 403  # fmt: skip


def test_other_organization_cannot_see_it(project, client, django_user_model):
    from rest_framework.test import APIClient

    from dexterhouse.apps.accounts.models import Membership, Organization

    cr = created(client, project)
    other = Organization.objects.create(slug="other", name="Other")
    stranger = django_user_model.objects.create_user(username="eve")
    Membership.objects.create(user=stranger, organization=other, role="owner")
    api = APIClient()
    api.force_login(stranger)
    assert api.get(f"/api/v1/change-requests/{cr['id']}").status_code == 404
