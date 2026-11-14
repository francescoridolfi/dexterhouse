# SPDX-License-Identifier: AGPL-3.0-or-later
"""`/projects/{id}/code/...`: read-only code views through the runner client."""

import pytest

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.services.actors import emit
from dexterhouse.apps.workspaces import services
from dexterhouse.apps.workspaces.code import public_url
from dexterhouse_schema.runner import ToolResult, WorkspaceChanged

pytestmark = pytest.mark.django_db
SHA = "a" * 40


def _live(project):
    workspace = services.request(project)
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="ready", container_id="c-1"),
        resume=False,
    )
    return workspace


def url(project, name, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"/api/v1/projects/{project.id}/code/{name}" + (f"?{query}" if query else "")


def test_tree_goes_through_a_read_only_system_task(client, project, runner_client):
    workspace = _live(project)
    runner_client.results["runner.system.ls_tree"] = ToolResult(
        ok=True,
        data={"commit": SHA, "branch": "main", "entries": [{"path": "a.py"}], "truncated": False},
    )
    response = client.get(url(project, "tree"))
    assert response.status_code == 200, response.json()
    assert response.json()["entries"] == [{"path": "a.py"}]
    task, message = runner_client.calls[-1]
    assert task == "runner.system.ls_tree"
    assert (message.workspace_id, message.ref) == (workspace.id, "HEAD")
    assert "Cache-Control" not in response or "immutable" not in response["Cache-Control"]
    pinned = client.get(url(project, "tree", ref=SHA))
    assert "immutable" in pinned["Cache-Control"]
    assert not any(t.startswith("runner.tool.") for t in runner_client.tasks())


def test_file_errors_map_to_problems(client, project, runner_client):
    _live(project)
    runner_client.results["runner.system.read_file"] = ToolResult(
        ok=True, data={"path": "src/a.py", "content": "x = 1\n", "binary": False}
    )
    ok = client.get(url(project, "file", path="src/a.py"))
    assert ok.json()["content"] == "x = 1\n"
    assert runner_client.calls[-1][1].path == "src/a.py"
    assert client.get(url(project, "file")).status_code == 400
    escape = client.get(url(project, "file", path="../etc/passwd"))
    assert escape.status_code == 400
    assert escape["Content-Type"] == "application/problem+json"
    assert client.get(url(project, "tree", ref="-x")).status_code == 400
    runner_client.results["runner.system.read_file"] = ToolResult.failure("not_found", "gone")
    assert client.get(url(project, "file", path="gone.py")).status_code == 404
    runner_client.results["runner.system.read_file"] = ToolResult.failure("timeout", "slow")
    down = client.get(url(project, "file", path="a.py"))
    assert down.status_code == 503
    assert down.json()["type"].endswith("/workspace-unavailable")


def test_no_live_workspace_is_503(client, project, runner_client):
    assert client.get(url(project, "tree")).status_code == 503
    assert runner_client.calls == []


def test_log_limits(client, project, runner_client):
    _live(project)
    runner_client.results["runner.system.commit_log"] = ToolResult(
        ok=True, data={"commits": [{"commit": SHA, "message": "feat: x"}], "branch": "main"}
    )
    body = client.get(url(project, "log", limit=5)).json()
    assert body == {
        "ref": "HEAD",
        "branch": "main",
        "commits": [{"commit": SHA, "message": "feat: x"}],
    }
    assert runner_client.calls[-1][1].max == 5
    assert client.get(url(project, "log", limit=0)).status_code == 400
    assert client.get(url(project, "log", limit="x")).status_code == 400


def test_location_lists_workspace_head_and_releases(client, project, runner_client):
    project.remote_repo_url = "https://github.com/acme/gymbook.git"
    project.save()
    workspace = _live(project)
    emit(
        project,
        "release.delivered",
        {
            "mode": "pull_request",
            "remote_url": project.remote_repo_url,
            "commit": "b" * 40,
            "pr_url": "https://github.com/acme/gymbook/pull/1",
        },
    )
    emit(
        project,
        "release.delivered",
        {
            "mode": "pull_request",
            "remote_url": project.remote_repo_url,
            "commit": "c" * 40,
            "pr_url": "https://github.com/acme/gymbook/pull/2",
            "branch": "dexterhouse/release-2",
        },
    )
    runner_client.results["runner.system.commit_log"] = ToolResult(
        ok=True, data={"commits": [{"commit": SHA, "message": "merge"}], "branch": "main"}
    )
    body = client.get(url(project, "location")).json()
    assert body["workspace"]["id"] == str(workspace.id)
    assert body["workspace"]["path"] == "/workspace"
    assert body["branch"] == "main"
    assert body["head"]["commit"] == SHA
    assert body["web_url"] == "https://github.com/acme/gymbook"
    assert [r["number"] for r in body["releases"]] == [2, 1]
    assert body["releases"][1]["branch"] == "dexterhouse/release-1"  # older event: no branch
    assert body["releases"][0]["pr_url"].endswith("/pull/2")
    assert Event.objects.filter(type="release.delivered").count() == 2


def test_location_without_workspace_still_answers(client, project, runner_client):
    body = client.get(url(project, "location")).json()
    assert body["workspace"] is None
    assert body["head"] is None
    assert body["unavailable"]
    assert body["releases"] == []


def test_permissions_follow_the_project(project, make_member, runner_client, django_user_model):
    from rest_framework.test import APIClient

    viewer = make_member("viewer")
    assert viewer.get(url(project, "location")).status_code == 200
    stranger = django_user_model.objects.create_user(username="eve")
    other = APIClient()
    other.force_login(stranger)
    assert other.get(url(project, "location")).status_code in (403, 404)
    assert APIClient().get(url(project, "tree")).status_code in (401, 403)


def test_public_url_drops_credentials():
    remote = "https://x:ghp_t@github.com/a/b"  # pragma: allowlist secret
    assert public_url(remote) == "https://github.com/a/b"
    assert public_url(None) is None
