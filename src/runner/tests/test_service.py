# SPDX-License-Identifier: AGPL-3.0-or-later
"""RunnerService with fake Docker (directories), fake MCP pool (in-process tools), fake Redis."""

import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dexterhouse_runner.docker_manager import RunnerError
from dexterhouse_runner.sessions import SessionError
from dexterhouse_schema.runner import (
    BranchCreate,
    CommitLog,
    Deliver,
    ExitCheck,
    Merge,
    PullRequest,
    ServerSpec,
    ToolInvoke,
    ToolList,
    Tree,
    WorkspaceCreate,
    WorkspaceDestroy,
    WorkspaceStatusQuery,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


def invoke(runner: SimpleNamespace, ws: uuid.UUID, tool: str, seq: int = 1, **args):
    return runner.service.invoke(
        ToolInvoke(
            workspace_id=ws,
            turn_id=uuid.uuid4(),
            seq=seq,
            tool=tool,
            args=args,
            agent_display_name="Developer",
        )
    )


def test_create_initialises_the_repository(
    stack: dict, runner: SimpleNamespace, workspace: uuid.UUID
):
    root = runner.docker.root(workspace)
    assert _git(root, "log", "--format=%s").strip() == "chore: initial commit"
    assert "detect-secrets-hook" in (root / ".git/hooks/pre-commit").read_text()
    assert _git(root, "config", "credential.helper").strip() == ""
    assert runner.callbacks.statuses() == ["creating", "ready"]
    env = runner.docker.containers[str(workspace)].env
    assert env["DH_STACK_ENV_KEYS"] == "APP_ENV"
    assert env["DH_WORKSPACE_QUOTA"] == str(5 * 1024**3)
    # idempotent: a second create reports the running workspace
    again = runner.service.create(
        WorkspaceCreate(project_id=uuid.uuid4(), workspace_id=workspace, stack=stack)
    )
    assert again.ok
    assert runner.callbacks.statuses()[-1] == "ready"


def test_create_refuses_images_outside_the_allowlist(stack: dict, runner: SimpleNamespace):
    ws = uuid.uuid4()
    result = runner.service.create(
        WorkspaceCreate(
            project_id=uuid.uuid4(),
            workspace_id=ws,
            stack={**stack, "workspace_image": "docker.io/evil/image:latest"},
        )
    )
    assert result.error.code == "workspace_not_ready"
    assert runner.callbacks.statuses() == ["error"]
    assert str(ws) not in runner.docker.containers


def test_create_failure_cleans_up(stack: dict, runner: SimpleNamespace):
    runner.docker.fail_create = RunnerError("workspace_not_ready", "pull failed")
    ws = uuid.uuid4()
    result = runner.service.create(
        WorkspaceCreate(project_id=uuid.uuid4(), workspace_id=ws, stack=stack)
    )
    assert not result.ok
    assert runner.docker.destroyed == [str(ws)]
    assert runner.callbacks.sent[-1][1].error_detail == "pull failed"


def test_status_and_destroy(runner: SimpleNamespace, workspace: uuid.UUID):
    assert (
        runner.service.status(WorkspaceStatusQuery(workspace_id=workspace)).data["status"]
        == "ready"
    )
    runner.service.destroy(WorkspaceDestroy(workspace_id=workspace, reason="inactive"))
    assert runner.pool.closed == [str(workspace)]
    assert runner.callbacks.statuses()[-1] == "destroyed"
    status = runner.service.status(WorkspaceStatusQuery(workspace_id=workspace))
    assert status.data["status"] == "destroyed"
    assert invoke(runner, workspace, "git_status").error.code == "workspace_not_ready"


def test_invoke_caches_by_turn_and_seq(runner: SimpleNamespace, workspace: uuid.UUID):
    message = ToolInvoke(
        workspace_id=workspace,
        turn_id=uuid.uuid4(),
        seq=3,
        tool="workspace_write",
        args={"path": "a.txt", "content": "x"},
    )
    first = runner.service.invoke(message)
    assert first.ok
    assert first.data["created"] is True
    second = runner.service.invoke(message)
    assert second.data["created"] is True  # served from the cache, not written again
    assert [c[0] for c in runner.pool.calls].count("workspace_write") == 1


def test_invoke_errors(runner: SimpleNamespace, workspace: uuid.UUID):
    assert invoke(runner, workspace, "workspace_read", path="../x").error.code == "workspace_escape"
    runner.redis.locked = True
    assert invoke(runner, workspace, "git_status", seq=2).error.code == "timeout"
    runner.redis.locked = False
    runner.pool.fail = TimeoutError("slow")
    assert invoke(runner, workspace, "git_status", seq=3).error.code == "timeout"
    runner.pool.fail = SessionError("crashed", broken=True)
    assert invoke(runner, workspace, "git_status", seq=4).error.code == "internal"
    assert runner.callbacks.statuses()[-1] == "ready"  # never reported as broken: code lives there


def test_exec_output_over_the_limit_goes_to_the_artifact(
    runner: SimpleNamespace, workspace: uuid.UUID
):
    result = invoke(
        runner, workspace, "workspace_exec", command="head -c 70000 /dev/zero | tr '\\0' b"
    )
    assert result.ok
    assert result.truncated
    assert len(result.data["stdout"]) == 64 * 1024
    assert "full_output" not in result.data
    assert len(result.artifact_payload) > 70000


def test_commit_sets_the_author_and_secrets_are_called_back(
    runner: SimpleNamespace, workspace: uuid.UUID
):
    root = runner.docker.root(workspace)
    runner.service.branch_create(
        BranchCreate(workspace_id=workspace, task_id=uuid.uuid4(), branch="task/T-01")
    )
    invoke(runner, workspace, "workspace_write", path="app.py", content="print(1)\n")
    with mock.patch(
        "dexterhouse_runner.workspace_mcp.gitops.scan_secrets", return_value={"app.py": 2}
    ):
        blocked = invoke(
            runner, workspace, "git_commit", seq=2, message="feat(T-01): app", all=True
        )
    assert blocked.error.code == "secrets_blocked"
    kind, message = runner.callbacks.sent[-1]
    assert kind == "secrets_blocked"
    assert (message.files, message.count) == (["app.py"], 2)
    with mock.patch("dexterhouse_runner.workspace_mcp.gitops.scan_secrets", return_value={}):
        done = invoke(
            runner,
            workspace,
            "git_commit",
            seq=3,
            message="feat(T-01): app",
            all=True,
            author="Someone Else",
        )
    assert done.ok
    assert _git(root, "log", "-1", "--format=%an").strip() == "Developer (DexterHouse)"


def test_list_tools_hides_the_author(runner: SimpleNamespace, workspace: uuid.UUID):
    tools = {
        t["name"]: t
        for t in runner.service.list_tools(ToolList(workspace_id=workspace)).data["tools"]
    }
    assert "author" not in tools["git_commit"]["input_schema"]["properties"]
    assert set(tools) >= {"workspace_exec", "workspace_run_tests", "git_diff", "workspace_move"}
    assert tools["workspace_move"]["input_schema"]["required"] == ["from", "to"]
    runner.pool.fail = SessionError("down")
    assert runner.service.list_tools(ToolList(workspace_id=workspace)).error.code == "internal"


def test_third_party_servers(runner: SimpleNamespace, workspace: uuid.UUID):
    bad = ServerSpec(name="evil", command=["/bin/sh", "-c", "x"])
    result = runner.service.list_tools(ToolList(workspace_id=workspace, server=bad))
    assert result.error.code == "tool_unknown"
    for n in range(3):
        runner.pool.servers.add((str(workspace), f"tool:s{n}"))
    extra = ServerSpec(name="s9", command=["uvx", "pkg@1.0.0"])
    assert runner.service.list_tools(ToolList(workspace_id=workspace, server=extra)).error.code == (
        "quota_exceeded"
    )


def test_branch_merge_and_log(runner: SimpleNamespace, workspace: uuid.UUID):
    root = runner.docker.root(workspace)
    task = uuid.uuid4()
    created = runner.service.branch_create(
        BranchCreate(workspace_id=workspace, task_id=task, branch="task/T-01")
    )
    assert created.data == {"branch": "task/T-01", "existed": False}
    again = runner.service.branch_create(
        BranchCreate(workspace_id=workspace, task_id=task, branch="task/T-01")
    )
    assert again.data["existed"] is True
    (root / "app.py").write_text("a = 1\nb = 2\n")
    with mock.patch("dexterhouse_runner.workspace_mcp.gitops.scan_secrets", return_value={}):
        merged = runner.service.merge(
            Merge(
                workspace_id=workspace,
                task_id=task,
                branch="task/T-01",
                message="merge(task/T-01): App",
            )
        )
    assert merged.ok, merged
    assert merged.data["files_changed"] == 1
    assert merged.data["insertions"] == 2
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    subjects = _git(root, "log", "--format=%s", "main").splitlines()
    assert subjects[0] == "merge(task/T-01): App"
    assert "chore(T-01): commit pending changes" in subjects
    repeat = runner.service.merge(
        Merge(
            workspace_id=workspace,
            task_id=task,
            branch="task/T-01",
            message="merge(task/T-01): App",
        )
    )
    assert repeat.data["already"] is True
    log = runner.service.commit_log(CommitLog(workspace_id=workspace))
    assert log.data["commits"][0]["message"] == "merge(task/T-01): App"
    missing = runner.service.merge(
        Merge(workspace_id=workspace, task_id=task, branch="task/T-99", message="m")
    )
    assert missing.error.code == "conflict"


def test_merge_conflict_is_aborted(runner: SimpleNamespace, workspace: uuid.UUID):
    root = runner.docker.root(workspace)
    task = uuid.uuid4()
    runner.service.branch_create(
        BranchCreate(workspace_id=workspace, task_id=task, branch="task/T-02")
    )
    (root / "f.txt").write_text("branch\n")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-qm", "feat: branch")
    _git(root, "checkout", "-q", "main")
    (root / "f.txt").write_text("main\n")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-qm", "feat: main")
    result = runner.service.merge(
        Merge(workspace_id=workspace, task_id=task, branch="task/T-02", message="m")
    )
    assert result.error.code == "conflict"
    assert _git(root, "status", "--porcelain").strip() == ""


def test_exit_checks_and_tree(stack: dict, runner: SimpleNamespace, workspace: uuid.UUID):
    ok = runner.service.exit_check(
        ExitCheck(
            workspace_id=workspace, kind="tests_pass", command=stack["test_command"], timeout_s=30
        )
    )
    assert ok.ok
    assert ok.data["summary"]["passed"] == 2
    assert ok.artifact_payload.startswith("$ python3")
    failed = runner.service.exit_check(
        ExitCheck(workspace_id=workspace, kind="command_ok", command="exit 4", timeout_s=30)
    )
    assert not failed.ok
    assert failed.exit_code == 4
    assert failed.error is None
    timed = runner.service.exit_check(
        ExitCheck(workspace_id=workspace, kind="command_ok", command="sleep 3", timeout_s=0.2)
    )
    assert not timed.ok
    assert "timed out" in timed.data["detail"]
    (runner.docker.root(workspace) / "pkg").mkdir()
    tree = runner.service.tree(Tree(workspace_id=workspace))
    assert "pkg/" in tree.data["tree"]


def test_exit_check_probe_wraps_the_command(runner: SimpleNamespace, workspace: uuid.UUID):
    with mock.patch.object(
        runner.service, "_tool", return_value={"exit_code": 0, "stdout": "probe ok"}
    ) as tool:
        result = runner.service.exit_check(
            ExitCheck(
                workspace_id=workspace,
                kind="command_ok",
                command="uvicorn app:app",
                probe_url="http://127.0.0.1:8000/health",
                timeout_s=60,
            )
        )
    assert result.ok
    command = tool.call_args[0][2]["command"]
    assert command.startswith("python3 -c ")
    assert "'uvicorn app:app'" in command
    assert "http://127.0.0.1:8000/health" in command


def test_deliver_redeems_the_grant_and_pushes(
    runner: SimpleNamespace, workspace: uuid.UUID, tmp_path: Path
):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    grant = uuid.uuid4()
    with mock.patch("dexterhouse_runner.service.redeem", return_value="tok-123") as redeem:
        result = runner.service.deliver(
            Deliver(
                workspace_id=workspace,
                mode="pull_request",
                remote_url=str(remote),
                token_ref=grant,
                branch_name="dexterhouse/release-1",
                pr=PullRequest(title="Release 1"),
            )
        )
    assert result.ok, result
    redeem.assert_called_once_with(grant, runner.settings)
    assert result.data["branch"] == "dexterhouse/release-1"
    assert result.data["pr_url"] is None  # a local remote has no pull request API
    assert _git(remote, "rev-parse", "dexterhouse/release-1").strip() == result.data["commit"]
    with mock.patch("dexterhouse_runner.service.redeem", side_effect=RunnerError("auth", "used")):
        again = runner.service.deliver(
            Deliver(
                workspace_id=workspace, mode="push_main", remote_url=str(remote), token_ref=grant
            )
        )
    assert again.error.code == "auth"


def test_heartbeat_reports_workspaces_and_egress(runner: SimpleNamespace, workspace: uuid.UUID):
    runner.docker.proxy_logs = (
        b"2026-11-01T10:00:01Z 1 TCP_DENIED/403 example.com\n"
        b"2026-11-01T10:00:02Z 2 TCP_DENIED/403 x\n2026-11-01T10:00:03Z 3 TCP_TUNNEL/200\n"
    )
    beat = runner.service.heartbeat()
    assert beat.active_workspaces == 1
    assert beat.workspaces == [workspace]
    assert beat.metrics["egress_denied_total"] >= 2
    again = runner.service.heartbeat()  # the same lines are not counted twice
    assert again.metrics["egress_denied_total"] == beat.metrics["egress_denied_total"]
    assert runner.callbacks.sent[-1][0] == "heartbeat"


def test_create_restarts_a_stopped_container(
    runner: SimpleNamespace, workspace: uuid.UUID, stack: dict
):
    container = runner.docker.containers[str(workspace)]
    container.status = "exited"

    def start():
        container.status = "running"

    container.start = start
    container.reload = lambda: None
    result = runner.service.create(
        WorkspaceCreate(project_id=uuid.uuid4(), workspace_id=workspace, stack=stack)
    )
    assert result.ok
    assert runner.docker.destroyed == []
