# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import uuid

import pytest

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn
from dexterhouse.apps.agents.services.mcp_client import McpError
from dexterhouse.apps.agents.services.packages import load_tool_catalog
from dexterhouse.apps.agents.services.tool_gateway import ToolGateway
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.gateway.messages import ToolCallPart
from dexterhouse.apps.projects.models import Artifact
from dexterhouse.apps.workflows import actions
from dexterhouse.apps.workspaces import events as ws_events
from dexterhouse.apps.workspaces import services
from dexterhouse.apps.workspaces.tools import RunnerTools
from dexterhouse_schema.runner import SecretsBlocked, ToolResult, WorkspaceChanged

STACK = {
    "language": "python",
    "framework": "fastapi",
    "workspace_image": "dexterhouse/workspace:python",
    "test_command": "uv run pytest",
    "run_command": "uv run uvicorn app:app",
    "ports": [8000],
    "healthcheck_path": "/health",
}
TOOLS = [
    {"name": "workspace_exec", "description": "Run", "input_schema": {"type": "object"}},
    {"name": "git_commit", "description": "Commit", "input_schema": {"type": "object"}},
    {"name": "workspace_run_tests", "description": "Tests", "input_schema": {"type": "object"}},
]


@pytest.fixture
def live(project, runner_client):
    project.stack = STACK
    project.save(update_fields=["stack"])
    workspace = services.request(project)
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="ready"), resume=False
    )
    return workspace


@pytest.fixture
def turn(project, organization):
    agent = AgentInstance.objects.create(
        organization=organization,
        project=project,
        role="developer",
        display_name="Developer",
        package_name="developer",
        package_version="0.1.0",
        package_path="",
        allowed_tools=["workspace.exec", "git.commit", "workspace.run_tests"],
    )
    return AgentTurn.objects.create(
        organization=organization, project=project, agent_instance=agent, purpose="test", inputs={}
    )


def binding(permission: str):
    found = load_tool_catalog().get(permission)
    assert found is not None, permission
    return found


def test_runner_tools_unavailable_without_workspace(turn, runner_client):
    tools = RunnerTools(turn)
    assert tools.list_tools(binding("workspace.exec")) is None
    assert not runner_client.calls
    with pytest.raises(McpError):
        tools.call(binding("workspace.exec"), {"command": "ls"}, 1)


def test_gateway_routes_runner_tools(live, turn, runner_client):
    runner_client.results["runner.tool.list"] = ToolResult(ok=True, data={"tools": TOOLS})
    runner_client.results["runner.tool.invoke"] = ToolResult(
        ok=True,
        exit_code=0,
        data={"exit_code": 0, "stdout": "hi"},
        truncated=True,
        artifact_payload="x" * 70_000,
    )
    gateway = ToolGateway(
        turn,
        pool=None,
        catalog=load_tool_catalog(),
        allowed=frozenset({"workspace.exec", "git.commit"}),
        runner=RunnerTools(turn),
    )
    names = [s.name for s in gateway.specs()]
    assert names == ["git.commit", "workspace.exec"]
    assert runner_client.tasks().count("runner.tool.list") == 1  # one listing per turn
    result = gateway.invoke(
        1, ToolCallPart(id="c1", name="workspace.exec", args={"command": "echo hi"})
    )
    body = json.loads(result.content)
    assert body["stdout"] == "hi"
    artifact = Artifact.objects.get(pk=body["artifact_id"])
    assert artifact.name == f"tool_outputs/{turn.id}-1.log"
    invoke = runner_client.calls[-1][1]
    assert invoke.tool == "workspace_exec"
    assert invoke.server is None
    assert invoke.agent_display_name == "Developer"
    assert invoke.turn_id == turn.id


def test_gateway_without_runner_marks_runner_tools(turn):
    gateway = ToolGateway(
        turn, pool=None, catalog=load_tool_catalog(), allowed=frozenset({"workspace.exec"})
    )
    assert gateway.specs() == []
    assert gateway.unavailable == {"workspace.exec": "runs_in_runner"}


def test_commit_and_tests_events(live, turn, runner_client, project):
    tools = RunnerTools(turn)
    runner_client.results["runner.tool.invoke"] = ToolResult(
        ok=True,
        data={"summary": {"passed": 3, "failed": 1, "skipped": 0}, "ok": False},
        artifact_payload="$ uv run pytest\n3 passed, 1 failed",
        duration_ms=1500,
    )
    outcome = tools.call(binding("workspace.run_tests"), {"scope": "all"}, 2)
    assert not outcome.is_error
    assert json.loads(outcome.content)["report_artifact_id"]
    completed = Event.objects.get(project_id=project.id, type="test.run.completed")
    assert completed.payload["failed"] == 1
    assert completed.payload["ok"] is False
    assert completed.payload["scope"] == "integration"
    assert completed.actor_type == "agent"
    runner_client.results["runner.tool.invoke"] = ToolResult.failure("secrets_blocked", "found")
    blocked = tools.call(binding("git.commit"), {"message": "feat: x"}, 3)
    assert blocked.is_error
    assert json.loads(blocked.content)["error"]["code"] == "secrets_blocked"


def test_secrets_blocked_callback_needs_a_task(turn, project):
    ws_events.secrets_blocked(
        SecretsBlocked(workspace_id=uuid.uuid4(), turn_id=turn.id, files=["a"], count=1)
    )
    assert not Event.objects.filter(type="secrets.blocked").exists()


def test_branch_merge_actions(live, project, runner_client):
    from dexterhouse.apps.workflows.models import Task

    task = Task(
        id=uuid.uuid4(), project=project, external_id="T-01", title="Courses", branch="task/T-01"
    )
    assert actions.branch_create(project, task).ok
    assert runner_client.calls[-1][1].branch == "task/T-01"
    runner_client.results["runner.system.merge"] = ToolResult(
        ok=True, data={"commit": "c0ffee", "files_changed": 2, "insertions": 10, "deletions": 1}
    )
    assert actions.merge(project, task).data["commit"] == "c0ffee"
    assert runner_client.calls[-1][1].message == "merge(task/T-01): Courses"
    merged = Event.objects.get(project_id=project.id, type="branch.merged")
    assert merged.payload["insertions"] == 10
    runner_client.results["runner.system.merge"] = ToolResult.failure("conflict", "x")
    failed = actions.merge(project, task)
    assert not failed.ok
    assert failed.data == {"commit": ""}
    runner_client.results["runner.system.branch_create"] = ToolResult.failure("conflict", "dirty")
    assert not actions.branch_create(project, task).ok


def test_actions_without_workspace(project, runner_client):
    from dexterhouse.apps.workflows.models import Task

    task = Task(id=uuid.uuid4(), project=project, external_id="T-01", title="x", branch="task/T-01")
    assert not actions.branch_create(project, task).ok
    assert actions.merge(project, task).data == {"commit": ""}
    assert actions.check_exit(project, "tests_pass", None).ok  # no workspace phase: as before
    assert not actions.workspace_create(project, None).ok  # no stack
    assert not runner_client.calls


def test_check_exit_runs_the_stack_commands(live, project, runner_client):
    runner_client.results["runner.system.exit_check"] = ToolResult(
        ok=False,
        exit_code=1,
        data={"summary": {"passed": 1, "failed": 2, "skipped": 0}, "tail": "E boom"},
        artifact_payload="$ uv run pytest\nE boom",
    )
    result = actions.check_exit(project, "tests_pass", None)
    assert not result.ok
    assert "exit code 1" in result.detail
    message = runner_client.calls[-1][1]
    assert (message.command, message.probe_url) == ("uv run pytest", None)
    runner_client.results["runner.system.exit_check"] = ToolResult(ok=True, exit_code=0, data={})
    assert actions.check_exit(project, "command_ok", "${stack.run_command}").ok
    message = runner_client.calls[-1][1]
    assert message.command == "uv run uvicorn app:app"
    assert message.probe_url == "http://127.0.0.1:8000/health"
    scopes = [
        e.payload["scope"]
        for e in Event.objects.filter(type="test.run.completed").order_by("created_at")
    ]
    assert scopes == ["integration", "smoke"]
    assert Event.objects.filter(type="test.run.started", actor_type="system").count() == 2


def test_deliver_action_is_queued(live, project, django_capture_on_commit_callbacks, monkeypatch):
    from dexterhouse.apps.workspaces import tasks

    queued = []
    monkeypatch.setattr(tasks.deliver, "delay", lambda *a: queued.append(a))
    assert actions.deliver(project, project).detail == "no remote repository"
    project.remote_repo_url = "https://github.com/acme/x"
    with django_capture_on_commit_callbacks(execute=True):
        assert actions.deliver(project, project).detail == "delivery queued"
    assert queued == [(str(project.id), str(project.id))]


def test_inputs_get_the_tree_and_the_commit_log(live, project, runner_client):
    from dexterhouse.apps.workflows.runners import inputs

    runner_client.results["runner.system.tree"] = ToolResult(
        ok=True, data={"tree": "app/\n  main.py (1 KB)"}
    )
    runner_client.results["runner.system.commit_log"] = ToolResult(
        ok=True,
        data={
            "commits": [
                {"commit": "a" * 40, "message": "feat(T-01): courses", "author": "Developer"}
            ]
        },
    )
    assert inputs.workspace_tree(project.id) == "app/\n  main.py (1 KB)"
    lines = inputs._release(None, project.id)
    assert "1 commits" in lines[0]
    assert lines[1] == "- aaaaaaaa feat(T-01): courses (Developer)"
    runner_client.results["runner.system.commit_log"] = ToolResult.failure("internal", "x")
    assert "No commit log" in inputs._release(None, project.id)[0]
