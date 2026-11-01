# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1 projects, artifacts, notes: roles, tokens, RFC 9457 errors, cursor pages."""

import pytest
from rest_framework.test import APIClient

from dexterhouse.apps.accounts.models import Membership, Organization
from dexterhouse.apps.accounts.services.tokens import create_token
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import Artifact, Project
from dexterhouse.common import crypto

pytestmark = pytest.mark.django_db
BODY = {"name": "GymBook", "brief": "A gym app.", "budget": 20}


def create(client, **extra):
    response = client.post("/api/v1/projects", {**BODY, **extra}, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def test_create_returns_draft_with_brief_artifact_and_event(client):
    data = create(client, remote_repo_url="https://github.com/acme/gymbook", remote_token="ghp_x")
    assert data["status"] == "draft"
    assert data["process"] == {"name": "software-house-default", "version": "1.0.0"}
    assert data["remote_token"] == "***set***"
    assert data["slug"] == "gymbook"
    project = Project.objects.get(pk=data["id"])
    assert crypto.decrypt(project.remote_token) == "ghp_x"
    brief = Artifact.objects.get(project=project)
    assert (brief.kind, brief.version, brief.content) == ("brief", 1, "A gym app.")
    event = Event.objects.get(project_id=project.id)
    assert (event.type, event.actor_type, event.actor_name) == ("project.created", "user", "ada")
    assert create(client)["slug"] == "gymbook-2"


@pytest.mark.parametrize(
    ("extra", "field"),
    [
        ({"process": "nope"}, "process"),
        ({"remote_repo_url": "http://github.com/x/y"}, "remote_repo_url"),
        ({"execution_mode": "yolo"}, "execution_mode"),
        ({"gate_overrides": {"approve_plan": "never"}}, "gate_overrides.approve_plan"),
        ({"stack": {"language": "cobol"}}, "data.framework"),
    ],
)
def test_create_validation_errors_are_problems(client, extra, field):
    response = client.post("/api/v1/projects", {**BODY, **extra}, format="json")
    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == 400
    assert body["instance"] == "/api/v1/projects"
    assert field in {e["field"] for e in body["errors"]}


def test_list_filters_and_paginates_with_cursor(client):
    for n in range(3):
        create(client, name=f"P{n}", execution_mode="autonomous" if n else "supervised")
    page = client.get("/api/v1/projects?limit=2").json()
    assert [p["name"] for p in page["results"]] == ["P2", "P1"]
    rest = client.get(page["next"]).json()
    assert [p["name"] for p in rest["results"]] == ["P0"]
    assert rest["next"] is None
    assert len(client.get("/api/v1/projects?execution_mode=autonomous").json()["results"]) == 2
    assert client.get("/api/v1/projects?q=P1").json()["results"][0]["name"] == "P1"


def test_roles_and_scopes(client, make_member, organization, user):
    project = create(client)
    viewer = make_member("viewer")
    member = make_member("member")
    assert viewer.get(f"/api/v1/projects/{project['id']}").status_code == 200
    denied = viewer.post("/api/v1/projects", BODY, format="json")
    assert denied.status_code == 403
    assert denied.json()["type"].endswith("/permission-denied")
    assert member.delete(f"/api/v1/projects/{project['id']}").status_code == 403
    _, read_only = create_token(
        organization=organization, user=user, name="ro", scopes=["projects:read"]
    )
    bearer = APIClient()
    bearer.credentials(HTTP_AUTHORIZATION=f"Bearer {read_only}")
    assert bearer.get("/api/v1/projects").status_code == 200
    assert bearer.post("/api/v1/projects", BODY, format="json").status_code == 403
    anonymous = APIClient().get("/api/v1/projects")
    assert anonymous.status_code in (401, 403)
    assert anonymous["Content-Type"] == "application/problem+json"


def test_other_organizations_are_invisible(client, user, django_user_model):
    project = create(client)
    other = Organization.objects.create(slug="acme", name="Acme")
    stranger = django_user_model.objects.create_user(username="eve")
    Membership.objects.create(user=stranger, organization=other, role="owner")
    api = APIClient()
    api.force_login(stranger)
    assert api.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert api.get("/api/v1/projects").json()["results"] == []
    Membership.objects.create(user=user, organization=other, role="viewer")
    assert client.get("/api/v1/projects", HTTP_X_ORGANIZATION="acme").json()["results"] == []
    assert client.get("/api/v1/projects", HTTP_X_ORGANIZATION="nope").status_code == 403
    _, token = create_token(organization=other, user=user, name="t", scopes=["projects:read"])
    bearer = APIClient()
    bearer.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert bearer.get("/api/v1/projects", HTTP_X_ORGANIZATION="default").status_code == 403


def test_patch_rules_and_budget_event(client):
    project = create(client, execution_mode="autonomous")
    url = f"/api/v1/projects/{project['id']}"
    patched = client.patch(url, {"brief": "New brief", "budget": 30}, format="json").json()
    assert patched["brief"] == "New brief"
    versions = Artifact.objects.filter(project_id=project["id"], kind="brief")
    assert sorted(versions.values_list("version", flat=True)) == [1, 2]
    changed = Event.objects.get(project_id=project["id"], type="project.budget_changed")
    assert changed.payload == {"old": "20.000000", "new": "30.000000"}
    client.post(f"{url}/start")
    locked = client.patch(url, {"brief": "Nope"}, format="json")
    assert locked.status_code == 409
    assert locked.json()["errors"] == [{"field": "brief", "message": "read-only after start"}]
    assert client.patch(url, {"name": "Renamed"}, format="json").json()["name"] == "Renamed"


def test_lifecycle_endpoints_and_soft_delete(client):
    project = create(client, execution_mode="autonomous")
    url = f"/api/v1/projects/{project['id']}"
    assert client.post(f"{url}/resume").status_code == 409
    assert client.post(f"{url}/start").json()["status"] == "running"
    assert client.post(f"{url}/start").status_code == 409
    assert client.post(f"{url}/pause").json()["status"] == "paused"
    assert client.delete(url).status_code == 409
    assert client.post(f"{url}/resume").json()["status"] == "running"
    assert client.post(f"{url}/retry").status_code == 409
    draft = create(client, name="Draft")
    assert client.delete(f"/api/v1/projects/{draft['id']}").status_code == 204
    archived = Project.objects.get(pk=draft["id"])
    assert archived.status == "archived"
    assert archived.deleted_at is not None
    assert draft["id"] not in [p["id"] for p in client.get("/api/v1/projects").json()["results"]]
    listed = client.get("/api/v1/projects?status=archived").json()["results"]
    assert [p["id"] for p in listed] == [draft["id"]]


def test_start_validation_reports_every_problem(client, settings):
    settings.WORKFLOWS_REPO_CHECKER = "tests.projects.test_project_api.refuse_repo"
    project = create(
        client,
        budget=0,
        remote_repo_url="https://github.com/acme/x",
        model_profile_overrides={"huge": {}},
    )
    response = client.post(f"/api/v1/projects/{project['id']}/start")
    assert response.status_code == 400
    fields = {e["field"] for e in response.json()["errors"]}
    assert fields == {"budget", "remote_repo_url", "model_profile_overrides"}
    assert not Event.objects.filter(project_id=project["id"], type="project.started").exists()


def refuse_repo(url: str, token: str | None) -> str:
    return f"cannot read {url}"


def test_artifacts_versions_diff_search_and_user_upload(client):
    project = create(client)
    base = f"/api/v1/projects/{project['id']}/artifacts"
    first = client.post(base, {"kind": "file", "name": "notes.md", "content": "a\nb\n"})
    second = client.post(base, {"kind": "file", "name": "notes.md", "content": "a\nc\n"})
    assert (first.status_code, second.json()["version"]) == (201, 2)
    assert client.post(base, {"kind": "review", "name": "x"}).status_code == 400
    bad = client.post(base, {"kind": "file", "name": "x", "data": {"a": 1}}, format="json")
    assert bad.status_code == 400
    artifact_id = second.json()["id"]
    versions = client.get(f"/api/v1/artifacts/{artifact_id}/versions").json()["results"]
    assert [v["version"] for v in versions] == [1, 2]
    diff = client.get(f"/api/v1/artifacts/{artifact_id}/diff?against=1").json()["diff"]
    assert "-b" in diff
    assert "+c" in diff
    assert client.get(f"/api/v1/artifacts/{artifact_id}/diff?against=x").status_code == 400
    assert client.get(f"/api/v1/artifacts/{artifact_id}/diff?against=9").status_code == 400
    latest = client.get(f"{base}?latest=true").json()["results"]
    assert sorted((a["kind"], a["version"]) for a in latest) == [("brief", 1), ("file", 2)]
    assert client.get(f"{base}?kind=brief").json()["results"][0]["kind"] == "brief"
    found = client.get(f"{base}?q=gym").json()["results"]
    assert [a["kind"] for a in found] == ["brief"]
    detail = client.get(f"/api/v1/artifacts/{artifact_id}").json()
    assert detail["content"] == "a\nc\n"
    stack = {
        "language": "python",
        "framework": "django",
        "workspace_image": "dexterhouse/workspace:python",
        "package_manager": "uv",
        "test_command": "uv run pytest",
        "run_command": "uv run manage.py runserver",
    }
    client.post(base, {"kind": "stack", "name": "stack.yaml", "data": stack}, format="json")
    assert Project.objects.get(pk=project["id"]).stack["framework"] == "django"


def test_notes(client, make_member):
    project = create(client)
    base = f"/api/v1/projects/{project['id']}/notes"
    note = client.post(base, {"content": "Use Tailwind, not Bootstrap"}, format="json")
    assert note.status_code == 201
    import uuid

    unknown = client.post(base, {"content": "x", "phase_run": str(uuid.uuid4())}, format="json")
    assert unknown.status_code == 400
    assert client.get(base).json()["results"][0]["content"].startswith("Use Tailwind")
    added = Event.objects.get(project_id=project["id"], type="note.added")
    assert added.payload["excerpt"] == "Use Tailwind, not Bootstrap"
    note_id = note.json()["id"]
    from dexterhouse.apps.projects.models import Note

    Note.objects.filter(pk=note_id).update(consumed_by_turn_ids=[uuid.uuid4()])
    assert client.delete(f"/api/v1/notes/{note_id}").status_code == 409
    Note.objects.filter(pk=note_id).update(consumed_by_turn_ids=[])
    assert client.delete(f"/api/v1/notes/{note_id}").status_code == 204


def test_snapshot_endpoint(client):
    project = create(client, execution_mode="autonomous")
    client.post(f"/api/v1/projects/{project['id']}/start")
    snapshot = client.get(f"/api/v1/projects/{project['id']}/snapshot").json()
    assert snapshot["type"] == "snapshot"
    assert [p["phase_id"] for p in snapshot["phases"]][:2] == ["analysis", "architecture"]
    assert snapshot["phases"][0]["status"] == "running"
    working = [a for a in snapshot["agents"] if a["status"] == "working"]
    assert [(a["role"], a["room"]) for a in working] == [("analyst", "meeting_room")]
    assert snapshot["budget"] == {"budget": "20.000000", "spent": "0.000000"}
    assert snapshot["last_event_id"]
