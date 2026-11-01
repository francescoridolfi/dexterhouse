# SPDX-License-Identifier: AGPL-3.0-or-later
"""Done criterion of E-05: `software-house-default` with the built-in agents, the `fake`
provider (demo responder) and the real runner (Docker) delivers a release to a bare repository.

The developer's files, the commits, the merges, the integration tests, the smoke probe and
the push all run for real in a `dh-test-ws-*` workspace; only the LLM is scripted.
"""

import subprocess

import pytest

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import Project
from dexterhouse.apps.workspaces.models import Workspace
from tests.live_runner import InProcessRunnerClient
from tests.workflows.conftest import drain, event_types
from tests.workflows.test_e2e import create

pytestmark = [
    pytest.mark.slow,  # Docker, a workspace container and a whole process with MCP servers
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("builtin_runtime"),
]


def _git(repo, *args: str) -> str:
    return subprocess.run(
        ["git", "--git-dir", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def test_release_is_delivered_to_a_bare_repository(client, live_runner, monkeypatch, tmp_path):
    from dexterhouse.apps.workspaces import client as client_module

    runner_client = InProcessRunnerClient(live_runner)
    monkeypatch.setattr(client_module, "import_string", lambda path: lambda: runner_client)
    live_runner.callbacks.forward = True
    remote = tmp_path / "gymbook.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    project = create(client, execution_mode="autonomous")
    Project.objects.filter(pk=project.pk).update(remote_repo_url=str(remote))
    try:
        assert client.post(f"/api/v1/projects/{project.id}/start").status_code == 200
        for _ in range(5):
            drain(project)
            project.refresh_from_db()
            if project.status != "running":
                break
        assert project.status == "completed", event_types(project)[-8:]
    finally:
        live_runner.callbacks.forward = False

    types = event_types(project)
    for expected in (
        "workspace.requested",
        "workspace.created",
        "branch.created",
        "commit.created",
        "branch.merged",
        "test.run.completed",
        "release.delivered",
    ):
        assert expected in types, expected
    tasks = Event.objects.filter(project_id=project.id, type="task.completed").count()
    assert types.count("branch.merged") == tasks
    assert all(e.payload["files_changed"] > 0 for e in Event.objects.filter(type="branch.merged"))
    system_runs = Event.objects.filter(
        project_id=project.id, type="test.run.completed", actor_type="system"
    )
    assert {e.payload["scope"] for e in system_runs} == {"integration", "smoke"}
    assert all(e.payload["ok"] for e in system_runs)
    delivered = Event.objects.get(project_id=project.id, type="release.delivered")
    assert delivered.payload["mode"] == "pull_request"

    head = _git(remote, "rev-parse", "dexterhouse/release-1").strip()
    assert head == delivered.payload["commit"]
    files = _git(remote, "ls-tree", "-r", "--name-only", head).split()
    assert "app/__init__.py" in files
    assert any(f.startswith("tests/test_01_") for f in files)
    authors = set(_git(remote, "log", "--format=%an", head).split("\n")) - {""}
    assert "Developer (DexterHouse)" in authors
    subjects = _git(remote, "log", "--format=%s", head)
    assert "merge(task/T-01)" in subjects
    assert "Co-authored-by" not in _git(remote, "log", "--format=%B", head)
    assert Workspace.objects.get(project=project).status == "ready"
    prepared = [c for t, c in runner_client.calls if t == "runner.system.commit_log"]
    assert prepared  # the PM's release notes read the commit log
