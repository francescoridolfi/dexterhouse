# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1: /packages, installs and consent, enable/disable/delete, validate."""

import io
import tarfile

import pytest

from dexterhouse.apps.agents.services import roster
from dexterhouse.apps.packages.models import Package

from .conftest import run

pytestmark = pytest.mark.django_db


def post_install(client, captured, **body):
    with captured(execute=True):
        response = client.post("/api/v1/packages", body, format="json")
    assert response.status_code == 202, response.json()
    return client.get(f"/api/v1/packages/installs/{response.json()['install_id']}").json()


def test_list_shows_global_and_own_packages(client, organization, pkg_dir):
    run(str(pkg_dir()), organization=organization)
    body = client.get("/api/v1/packages?kind=agent&limit=200").json()
    names = {p["name"]: p for p in body["results"]}
    assert names["analyst"]["global"] is True
    assert names["analyst"]["source"] == "builtin"
    mine = names["security-reviewer"]
    assert (mine["global"], mine["version"], mine["role"], mine["risk"]) == (
        False,
        "1.0.0",
        "security_reviewer",
        "low",
    )
    processes = client.get("/api/v1/packages?kind=process&source=builtin").json()["results"]
    assert {p["name"] for p in processes} == {"code-review-only", "software-house-default"}
    disabled = client.get("/api/v1/packages?status=disabled&limit=200").json()["results"]
    assert "security-reviewer" not in {p["name"] for p in disabled}  # the parked test team is


def test_detail_lists_versions_permissions_and_projects(client, organization, pkg_dir, project):
    package = run(str(pkg_dir()), organization=organization).package_version.package
    roster.ensure_agent(project, "security_reviewer")
    project.status = "running"
    project.save()
    body = client.get(f"/api/v1/packages/{package.id}").json()
    assert body["versions"][0]["manifest"]["name"] == "security-reviewer"
    assert body["versions"][0]["definition"]["role"] == "security_reviewer"
    assert body["permissions"][0]["id"] == "memory.search"
    assert body["projects"] == [str(project.id)]


def test_install_with_consent_flow(
    client, organization, pkg_dir, django_capture_on_commit_callbacks
):
    src = pkg_dir(name="git-tools", kind="tool")
    install = post_install(client, django_capture_on_commit_callbacks, source=str(src))
    assert install["status"] == "awaiting_consent"
    assert install["consent_required"]["permissions"][0]["id"] == "git.push"
    response = client.post(
        f"/api/v1/packages/installs/{install['install_id']}/consent",
        {"accept": True},
        format="json",
    )
    assert response.json()["status"] == "installed"
    again = client.post(
        f"/api/v1/packages/installs/{install['install_id']}/consent",
        {"accept": True},
        format="json",
    )
    assert again.status_code == 409
    assert again.json()["type"].endswith("invalid-transition")


def test_install_with_confirmed_permissions(client, pkg_dir, django_capture_on_commit_callbacks):
    src = pkg_dir(name="git-tools", kind="tool")
    install = post_install(
        client,
        django_capture_on_commit_callbacks,
        source=str(src),
        confirm_permissions=["git.push"],
    )
    assert install["status"] == "installed"
    assert install["package"]
    assert install["errors"] == []


def test_install_errors_are_reported(client, tmp_path, django_capture_on_commit_callbacks):
    install = post_install(
        client, django_capture_on_commit_callbacks, source=str(tmp_path / "missing")
    )
    assert (install["status"], install["reason"]) == ("failed", "fetch")
    bad = client.post("/api/v1/packages", {"source": "git+https://x/y"}, format="json")
    assert bad.status_code == 400
    both = client.post("/api/v1/packages", {"source": "a", "marketplace": "b"}, format="json")
    assert both.status_code == 400
    url = client.post("/api/v1/packages", {"marketplace": "git+https://x/y@v1"}, format="json")
    assert url.status_code == 400
    path = client.post("/api/v1/packages", {"marketplace": "a/b"}, format="json")
    assert path.status_code == 400


def test_enable_disable_delete(client, organization, pkg_dir):
    package = run(str(pkg_dir()), organization=organization).package_version.package
    disabled = client.post(f"/api/v1/packages/{package.id}/disable", {"reason": "x"}, format="json")
    assert disabled.json()["status"] == "disabled"
    assert client.post(f"/api/v1/packages/{package.id}/disable").status_code == 409
    assert client.post(f"/api/v1/packages/{package.id}/enable").json()["status"] == "installed"
    assert client.delete(f"/api/v1/packages/{package.id}").status_code == 204
    assert client.get(f"/api/v1/packages/{package.id}").status_code == 404


def test_delete_in_use_is_a_conflict(client, organization, pkg_dir, project):
    package = run(str(pkg_dir()), organization=organization).package_version.package
    roster.ensure_agent(project, "security_reviewer")
    project.status = "waiting"
    project.save()
    response = client.delete(f"/api/v1/packages/{package.id}")
    assert response.status_code == 409
    assert response.json()["errors"] == [{"field": "projects", "message": str(project.id)}]


def test_permissions(make_member, client, organization, pkg_dir):
    member = make_member("member")
    assert member.get("/api/v1/packages").status_code == 200
    assert member.post("/api/v1/packages", {"source": "x"}, format="json").status_code == 403
    builtin = Package.objects.get(name="analyst")
    assert client.post(f"/api/v1/packages/{builtin.id}/disable").status_code == 403
    assert client.delete(f"/api/v1/packages/{builtin.id}").status_code == 403
    other = run(str(pkg_dir()), organization=None).package_version.package
    assert client.get(f"/api/v1/packages/{other.id}").json()["global"] is True


def test_installs_are_scoped_to_the_organization(client, pkg_dir):
    foreign = run(str(pkg_dir()), organization=None)
    assert client.get(f"/api/v1/packages/installs/{foreign.id}").status_code == 404


def test_validate_path_and_archive(make_member, pkg_dir, settings):
    member = make_member("member")
    src = pkg_dir()
    ok = member.post("/api/v1/packages/validate", {"path": str(src)}, format="json").json()
    assert ok == {"valid": True, "errors": [], "warnings": []}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        tar.add(src, arcname="security-reviewer")
    buffer.seek(0)
    buffer.name = "pkg.tar.gz"
    body = member.post("/api/v1/packages/validate", {"archive": buffer}, format="multipart")
    assert body.json()["valid"] is True
    (src / "agent.yaml").write_text("schema: 1\n")
    bad = member.post("/api/v1/packages/validate", {"path": str(src)}, format="json").json()
    assert bad["valid"] is False
    assert bad["errors"][0]["path"] == "agent.yaml"
    junk = io.BytesIO(b"not a tar")
    junk.name = "x.tar"
    response = member.post("/api/v1/packages/validate", {"archive": junk}, format="multipart")
    assert response.status_code == 400
    settings.PACKAGES_ALLOW_LOCAL = False
    response = member.post("/api/v1/packages/validate", {"path": str(src)}, format="json")
    assert response.status_code == 400
