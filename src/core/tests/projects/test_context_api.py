# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1 context documents (docs/specs/context-documents.md, section API)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from dexterhouse.apps.projects.models import ProjectStatus

pytestmark = pytest.mark.django_db(transaction=True)
TEXT = b"# Analysis\n\nThe booking API answers in 200 ms.\n"


@pytest.fixture(autouse=True)
def context_dir(settings, tmp_path):
    settings.CONTEXT_DIR = tmp_path / "context"


def upload(api, project, name="analysis.md", content=TEXT, **extra):
    file = SimpleUploadedFile(name, content, content_type="application/octet-stream")
    return api.post(
        f"/api/v1/projects/{project.id}/context", {"file": file, **extra}, format="multipart"
    )


def test_upload_list_detail_and_download(client, project):
    response = upload(client, project, title="Tech analysis")
    assert response.status_code == 202, response.json()
    doc = response.json()
    assert doc["name"] == "context/analysis.md"
    assert doc["title"] == "Tech analysis"
    assert doc["status"] in {"processing", "processed"}
    listed = client.get(f"/api/v1/projects/{project.id}/context").json()["results"]
    assert [d["id"] for d in listed] == [doc["id"]]
    assert listed[0]["status"] == "processed"
    assert "content" not in listed[0]
    detail = client.get(f"/api/v1/context/{doc['id']}").json()
    assert detail["content"] == TEXT.decode()
    download = client.get(f"/api/v1/context/{doc['id']}/download")
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == TEXT
    assert "analysis.md" in download["Content-Disposition"]


def test_invalid_files_are_problems_on_the_file_field(client, project):
    response = upload(client, project, name="tool.exe", content=b"MZ")
    assert response.status_code == 400
    assert response.json()["errors"][0]["field"] == "file"
    missing = client.post(f"/api/v1/projects/{project.id}/context", {}, format="multipart")
    assert missing.status_code == 400


def test_viewer_reads_but_cannot_upload_or_deactivate(client, project, make_member):
    doc = upload(client, project).json()
    viewer = make_member("viewer")
    assert viewer.get(f"/api/v1/projects/{project.id}/context").status_code == 200
    assert upload(viewer, project).status_code == 403
    assert viewer.delete(f"/api/v1/context/{doc['id']}").status_code == 403


def test_member_deactivates_only_own_documents_admin_any(client, project, make_member):
    mine_by_owner = upload(client, project).json()
    member = make_member("member")
    theirs = upload(member, project, name="member.md").json()
    assert member.delete(f"/api/v1/context/{mine_by_owner['id']}").status_code == 403
    gone = member.delete(f"/api/v1/context/{theirs['id']}")
    assert gone.status_code == 200
    assert gone.json()["active"] is False
    assert client.delete(f"/api/v1/context/{mine_by_owner['id']}").status_code == 200
    assert client.get(f"/api/v1/projects/{project.id}/context").json()["results"] == []
    everything = client.get(f"/api/v1/projects/{project.id}/context?all=1").json()["results"]
    assert len(everything) == 2


def test_archived_project_refuses_uploads(client, project):
    project.status = ProjectStatus.ARCHIVED
    project.save(update_fields=["status"])
    assert upload(client, project).status_code == 409


def test_other_organizations_cannot_see_documents(client, project, django_user_model):
    from rest_framework.test import APIClient

    from dexterhouse.apps.accounts.models import Membership, Organization

    doc = upload(client, project).json()
    other_org = Organization.objects.create(slug="other", name="Other")
    stranger = django_user_model.objects.create_user(username="eve")
    Membership.objects.create(user=stranger, organization=other_org, role="owner")
    api = APIClient()
    api.force_login(stranger)
    assert api.get(f"/api/v1/context/{doc['id']}").status_code == 404
    assert api.get(f"/api/v1/context/{doc['id']}/download").status_code == 404
