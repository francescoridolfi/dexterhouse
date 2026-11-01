# SPDX-License-Identifier: AGPL-3.0-or-later
"""T5, T10, T11: secrets in commits, the git token, protected branches, one-time grants."""

import subprocess
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from django.test import Client
from django.utils import timezone

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.workflows.models import PhaseRun, ProcessRun, Task
from dexterhouse.apps.workspaces import delivery as core_delivery
from dexterhouse.apps.workspaces import services
from dexterhouse.apps.workspaces.grants import create_grant
from dexterhouse.apps.workspaces.models import SecretGrant, Workspace
from dexterhouse.common import crypto
from dexterhouse_runner import delivery as runner_delivery
from dexterhouse_schema.runner import BranchCreate, Deliver, WorkspaceChanged
from tests.live_runner import (
    InProcessRunnerClient,
    create_workspace,
    destroy_workspace,
    output,
    run,
    tool,
)

pytestmark = [pytest.mark.security, pytest.mark.django_db(transaction=True)]
TOKEN = "ghp_e05securitytesttoken0000000000000000"  # pragma: allowlist secret
AWS = "AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE\n"  # pragma: allowlist secret


@pytest.fixture
def workspace(live_runner):
    workspace_id = create_workspace(live_runner)
    yield workspace_id
    destroy_workspace(live_runner, workspace_id)


@pytest.fixture
def in_process(live_runner, monkeypatch):
    from dexterhouse.apps.workspaces import client as client_module

    client = InProcessRunnerClient(live_runner)
    monkeypatch.setattr(client_module, "import_string", lambda path: lambda: client)
    live_runner.callbacks.forward = True
    yield client
    live_runner.callbacks.forward = False


def _bound(project, workspace_id):
    """A core Workspace row mirroring the runner's container."""
    row = Workspace.objects.create(id=workspace_id, project=project, stack={}, status="requested")
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace_id, status="ready"), resume=False
    )
    return row


def _task_turn(project, organization):
    run_row = ProcessRun.objects.create(
        project=project, process_name="p", process_version="1", definition={}, status="running"
    )
    phase = PhaseRun.objects.create(
        process_run=run_row, phase_id="implementation", position=0, room="open_space"
    )
    task = Task.objects.create(
        project=project,
        phase_run=phase,
        external_id="T-01",
        title="x",
        assigned_role="developer",
        branch="task/T-01",
        max_iterations=3,
    )
    agent = AgentInstance.objects.create(
        organization=organization,
        project=project,
        role="developer",
        display_name="Developer",
        package_name="d",
        package_version="1",
        package_path="",
        allowed_tools=["git.commit"],
    )
    return task, AgentTurn.objects.create(
        organization=organization,
        project=project,
        agent_instance=agent,
        task=task,
        phase_run=phase,
        purpose="t",
        inputs={},
    )


def test_st09_commit_with_a_secret_is_blocked(
    live_runner, workspace, in_process, project, organization
):
    _bound(project, workspace)
    task, turn = _task_turn(project, organization)
    live_runner.branch_create(
        BranchCreate(workspace_id=workspace, task_id=task.id, branch="task/T-01")
    )
    assert tool(live_runner, workspace, "workspace_write", path=".env", content=AWS).ok
    before = run(live_runner, workspace, "git rev-parse HEAD").data["stdout"]
    from dexterhouse_schema.runner import ToolInvoke

    blocked = live_runner.invoke(
        ToolInvoke(
            workspace_id=workspace,
            turn_id=turn.id,
            seq=1,
            tool="git_commit",
            args={"message": "feat(T-01): config", "all": True},
        )
    )
    assert blocked.error.code == "secrets_blocked"
    assert ".env" in blocked.error.detail
    assert run(live_runner, workspace, "git rev-parse HEAD").data["stdout"] == before
    event = Event.objects.get(project_id=project.id, type="secrets.blocked")
    assert event.payload["files"] == [".env"]
    assert event.payload["task_id"] == str(task.id)
    # the hook also stops a commit made by hand with workspace.exec
    manual = run(live_runner, workspace, "git add .env && git commit -m 'feat: sneaky'")
    assert manual.data["exit_code"] != 0
    assert run(live_runner, workspace, "git rev-parse HEAD").data["stdout"] == before


def _bare(tmp_path: Path, name: str = "remote.git") -> Path:
    remote = tmp_path / name
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def test_st10_the_token_never_enters_the_workspace(
    live_runner, workspace, live_server, project, tmp_path, monkeypatch
):
    project.remote_token = crypto.encrypt(TOKEN)
    project.save(update_fields=["remote_token"])
    monkeypatch.setattr(live_runner.settings, "CORE_URL", live_server.url)
    remote = _bare(tmp_path)
    tool(live_runner, workspace, "workspace_write", path="README.md", content="# release\n")
    run(live_runner, workspace, "git add README.md && git commit -qm 'docs: readme'")
    seen: list[str] = []
    real = runner_delivery._run_git

    def spy(argv, env, cwd):
        if not seen:  # while the delivery holds the token, look inside the workspace
            seen.append(
                output(
                    run(
                        live_runner,
                        workspace,
                        "env; cat ~/.git-credentials; git config -l; "
                        "ls -la /tmp /home/dh; cat /proc/*/environ 2>/dev/null | tr '\\0' '\\n'",
                    )
                )
            )
        assert TOKEN not in " ".join(argv)
        return real(argv, env, cwd)

    monkeypatch.setattr(runner_delivery, "_run_git", spy)
    grant = create_grant(project)
    result = live_runner.deliver(
        Deliver(
            workspace_id=workspace,
            mode="pull_request",
            remote_url=str(remote),
            token_ref=grant.id,
            branch_name="dexterhouse/release-1",
        )
    )
    assert result.ok, result.error
    assert seen
    assert TOKEN not in seen[0]
    assert (
        subprocess.run(
            ["git", "-C", str(remote), "rev-parse", "dexterhouse/release-1"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == result.data["commit"]
    )
    assert SecretGrant.objects.get(pk=grant.id).consumed_at is not None
    again = live_runner.deliver(
        Deliver(
            workspace_id=workspace,
            mode="pull_request",
            remote_url=str(remote),
            token_ref=grant.id,
            branch_name="dexterhouse/release-1",
        )
    )
    assert again.error.code == "auth"  # the grant was used once


def test_st15_protected_main_and_never_force(
    live_runner, workspace, in_process, project, tmp_path, monkeypatch
):
    remote = _bare(tmp_path)
    hook = remote / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\necho 'GH006: Protected branch update failed for refs/heads/main.' >&2\nexit 1\n"
    )
    hook.chmod(0o755)
    argvs: list[list[str]] = []
    real = runner_delivery._run_git
    monkeypatch.setattr(
        runner_delivery,
        "_run_git",
        lambda argv, env, cwd: argvs.append(argv) or real(argv, env, cwd),
    )
    _bound(project, workspace)
    project.remote_repo_url = str(remote)
    project.delivery_mode = "push_main"
    project.save(update_fields=["remote_repo_url", "delivery_mode"])
    assert core_delivery.deliver(project.id, uuid.uuid4()) == "failed"
    failed = Event.objects.get(project_id=project.id, type="release.failed")
    assert failed.payload["error_code"] == "protected_branch"
    flat = [a for argv in argvs for a in argv]
    assert "--force" not in flat
    assert "-f" not in flat
    assert not any(a.startswith("+") for a in flat)


def test_st16_grants_are_one_time(live_server, project):
    project.remote_token = crypto.encrypt(TOKEN)
    project.save(update_fields=["remote_token"])
    http = Client()
    grant = create_grant(project)
    assert http.get(f"/internal/secrets/{grant.id}").status_code == 401
    assert (
        http.get(f"/internal/secrets/{grant.id}", HTTP_X_RUNNER_KEY="test-runner-key").status_code
        == 200
    )
    assert (
        http.get(f"/internal/secrets/{grant.id}", HTTP_X_RUNNER_KEY="test-runner-key").status_code
        == 404
    )
    late = create_grant(project)
    SecretGrant.objects.filter(pk=late.pk).update(
        created_at=timezone.now() - timedelta(seconds=61),
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    assert (
        http.get(f"/internal/secrets/{late.id}", HTTP_X_RUNNER_KEY="test-runner-key").status_code
        == 404
    )
