# SPDX-License-Identifier: AGPL-3.0-or-later
"""Snapshots and restore (ADR-0018) on temporary git repositories and the fake Docker."""

import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from runner_helpers import STACK, git

from dexterhouse_runner import delivery, snapshots
from dexterhouse_runner.docker_manager import RunnerError
from dexterhouse_schema.runner import (
    Restore,
    Snapshot,
    SnapshotDrop,
    WorkspaceChanged,
    WorkspaceCreate,
)


@pytest.fixture
def snap_dir(runner: SimpleNamespace, tmp_path: Path) -> Path:
    directory = tmp_path / "snapshots"
    runner.settings.RUNNER_SNAPSHOT_DIR = str(directory)
    return directory


def _commit(root: Path, name: str, text: str, message: str) -> str:
    (root / name).write_text(text, encoding="utf-8")
    git(root, "add", name)
    git(root, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def _create(runner: SimpleNamespace, project: uuid.UUID, restore: Restore | None = None):
    ws = uuid.uuid4()
    result = runner.service.create(
        WorkspaceCreate(project_id=project, workspace_id=ws, stack=STACK, restore=restore)
    )
    return ws, result


def test_snapshot_then_restore_keeps_history_and_branches(runner: SimpleNamespace, snap_dir: Path):
    project = uuid.uuid4()
    ws, created = _create(runner, project)
    assert created.ok
    root = runner.docker.root(ws)
    head = _commit(root, "app.py", "print('v1')\n", "feat: v1")
    git(root, "branch", "feature/x")
    git(root, "tag", "v1")

    result = runner.service.snapshot(Snapshot(workspace_id=ws, project_id=project))
    assert result.ok, result
    bundle = snap_dir / f"{project}.bundle"
    assert result.data == {"commit": head, "size": bundle.stat().st_size}
    assert [p.name for p in snap_dir.iterdir()] == [bundle.name]  # no temporary left

    restored_ws, restored = _create(runner, project, Restore(source="snapshot"))
    assert restored.ok, restored
    assert restored.data["restored_commit"] == head
    changed = [m for k, m in runner.callbacks.sent if k == "workspace_changed"][-1]
    assert isinstance(changed, WorkspaceChanged)
    assert (changed.status, changed.restored_commit) == ("ready", head)
    new_root = runner.docker.root(restored_ws)
    assert (new_root / "app.py").read_text() == "print('v1')\n"
    assert git(new_root, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert git(new_root, "status", "--porcelain").strip() == ""
    assert "feature/x" in git(new_root, "branch", "--list")
    assert git(new_root, "tag").split() == ["v1"]
    assert (new_root / ".git/hooks/pre-commit").is_file()  # _init_repo ran on top
    assert git(new_root, "remote").strip() == ""


def test_snapshot_replaces_the_previous_bundle(runner: SimpleNamespace, snap_dir: Path):
    project = uuid.uuid4()
    ws, _ = _create(runner, project)
    first = runner.service.snapshot(Snapshot(workspace_id=ws, project_id=project))
    head = _commit(runner.docker.root(ws), "b.txt", "b\n", "feat: b")
    second = runner.service.snapshot(Snapshot(workspace_id=ws, project_id=project))
    assert first.ok
    assert second.ok
    assert second.data["commit"] == head != first.data["commit"]
    assert len(list(snap_dir.iterdir())) == 1


def test_snapshot_ignores_the_agents_git_config_and_hooks(
    runner: SimpleNamespace, snap_dir: Path, tmp_path: Path
):
    project = uuid.uuid4()
    ws, _ = _create(runner, project)
    root = runner.docker.root(ws)
    marker = tmp_path / "pwned"
    git(root, "config", "core.fsmonitor", f"touch {marker}")
    git(root, "config", "alias.bundle", f"!touch {marker}")
    (root / ".git/objects/info").mkdir(parents=True, exist_ok=True)
    (root / ".git/objects/info/alternates").write_text("/nonexistent/objects\n")
    result = runner.service.snapshot(Snapshot(workspace_id=ws, project_id=project))
    assert result.ok, result
    assert not marker.exists()


def test_snapshot_refuses_a_workspace_of_another_project(
    runner: SimpleNamespace, snap_dir: Path, workspace: uuid.UUID
):
    runner.docker.containers[str(workspace)].labels["dexterhouse.project"] = str(uuid.uuid4())
    result = runner.service.snapshot(Snapshot(workspace_id=workspace, project_id=uuid.uuid4()))
    assert result.error is not None
    assert result.error.code == "invalid"
    assert not snap_dir.exists() or not list(snap_dir.iterdir())


def test_snapshot_of_a_missing_workspace(runner: SimpleNamespace, snap_dir: Path):
    result = runner.service.snapshot(Snapshot(workspace_id=uuid.uuid4(), project_id=uuid.uuid4()))
    assert result.error is not None
    assert result.error.code == "workspace_not_ready"


def test_failed_bundle_leaves_the_previous_one(runner: SimpleNamespace, snap_dir: Path):
    project = uuid.uuid4()
    ws, _ = _create(runner, project)
    assert runner.service.snapshot(Snapshot(workspace_id=ws, project_id=project)).ok
    before = (snap_dir / f"{project}.bundle").read_bytes()

    def failing(argv, env, cwd):
        if "bundle" in argv:
            Path(argv[-2]).write_bytes(b"partial")
            return subprocess.CompletedProcess(argv, 1, b"", b"fatal: disk full")
        return delivery._run_git(argv, env, cwd)

    with mock.patch.object(snapshots, "_run_git", failing):
        result = runner.service.snapshot(Snapshot(workspace_id=ws, project_id=project))
    assert not result.ok
    assert (snap_dir / f"{project}.bundle").read_bytes() == before
    assert len(list(snap_dir.iterdir())) == 1


def test_snapshot_drop_is_idempotent(runner: SimpleNamespace, snap_dir: Path):
    project = uuid.uuid4()
    ws, _ = _create(runner, project)
    assert runner.service.snapshot(Snapshot(workspace_id=ws, project_id=project)).ok
    first = runner.service.snapshot_drop(SnapshotDrop(project_id=project))
    again = runner.service.snapshot_drop(SnapshotDrop(project_id=project))
    assert (first.ok, first.data) == (True, {"deleted": True})
    assert (again.ok, again.data) == (True, {"deleted": False})
    assert not (snap_dir / f"{project}.bundle").exists()


def test_restore_without_a_snapshot_fails_the_workspace(runner: SimpleNamespace, snap_dir: Path):
    ws, result = _create(runner, uuid.uuid4(), Restore(source="snapshot"))
    assert not result.ok
    assert result.error is not None
    assert result.error.code == "workspace_not_ready"
    assert "restore from the snapshot failed" in result.error.detail
    assert runner.callbacks.statuses()[-1] == "error"
    assert str(ws) in runner.docker.destroyed


def _bare_remote(tmp_path: Path) -> tuple[Path, str]:
    work = tmp_path / "upstream"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    _commit(work, "README.md", "main\n", "docs: main")
    git(work, "checkout", "-q", "-b", "dexterhouse/release-1")
    head = _commit(work, "app.py", "release\n", "feat: release")
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(work), str(remote)], check=True, capture_output=True
    )
    return remote, head


def test_restore_from_the_remote_branch_as_main(
    runner: SimpleNamespace, snap_dir: Path, tmp_path: Path
):
    remote, head = _bare_remote(tmp_path)
    grant = uuid.uuid4()
    argvs: list[list[str]] = []

    def spy(argv, env, cwd):
        argvs.append(argv)
        return delivery._run_git(argv, env, cwd)

    with (
        mock.patch("dexterhouse_runner.service.redeem", return_value="tok-secret") as redeem,
        mock.patch.object(snapshots, "_run_git", spy),
    ):
        ws, result = _create(
            runner,
            uuid.uuid4(),
            Restore(
                source="remote",
                remote_url=str(remote),
                token_ref=grant,
                branch="dexterhouse/release-1",
            ),
        )
    assert result.ok, result
    redeem.assert_called_once_with(grant, runner.settings)
    assert result.data["restored_commit"] == head
    root = runner.docker.root(ws)
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert (root / "app.py").read_text() == "release\n"
    assert not any("tok-secret" in a for argv in argvs for a in argv)
    leaked = subprocess.run(
        ["grep", "-r", "-l", "tok-secret", str(root)], capture_output=True, check=False
    )
    assert leaked.stdout == b""
    assert str(remote) not in (root / ".git/config").read_text()
    assert not (root / ".git/FETCH_HEAD").exists()


def test_restore_from_a_missing_remote_branch(
    runner: SimpleNamespace, snap_dir: Path, tmp_path: Path
):
    remote, _ = _bare_remote(tmp_path)
    _, result = _create(
        runner,
        uuid.uuid4(),
        Restore(source="remote", remote_url=str(remote), branch="nope"),
    )
    assert not result.ok
    assert result.error is not None
    assert result.error.detail.startswith("restore from the remote failed")


def test_restore_from_the_remote_needs_a_url(runner: SimpleNamespace, snap_dir: Path):
    _, result = _create(runner, uuid.uuid4(), Restore(source="remote"))
    assert not result.ok
    assert result.error is not None
    assert "needs a remote_url" in result.error.detail


def test_a_failed_grant_fails_the_restore(runner: SimpleNamespace, snap_dir: Path):
    with mock.patch(
        "dexterhouse_runner.service.redeem", side_effect=RunnerError("auth", "already used")
    ):
        _, result = _create(
            runner,
            uuid.uuid4(),
            Restore(
                source="remote", remote_url="https://example.invalid/r.git", token_ref=uuid.uuid4()
            ),
        )
    assert not result.ok
    assert result.error is not None
    assert result.error.detail == "restore from the remote failed: already used"


def test_a_retried_restoring_create_reports_the_commit(runner: SimpleNamespace, snap_dir: Path):
    project = uuid.uuid4()
    ws, _ = _create(runner, project)
    assert runner.service.snapshot(Snapshot(workspace_id=ws, project_id=project)).ok
    restore = Restore(source="snapshot")
    message = WorkspaceCreate(
        project_id=project, workspace_id=uuid.uuid4(), stack=STACK, restore=restore
    )
    first = runner.service.create(message)
    again = runner.service.create(message)
    assert first.ok
    assert again.ok
    assert again.data["restored_commit"] == first.data["restored_commit"]


def test_task_methods_cover_the_snapshot_messages():
    from dexterhouse_runner.service import TASK_METHODS
    from dexterhouse_schema.runner import RUNNER_TASKS

    assert set(TASK_METHODS) == set(RUNNER_TASKS)
    assert TASK_METHODS["runner.system.snapshot"] == "snapshot"
    assert TASK_METHODS["runner.system.snapshot_drop"] == "snapshot_drop"
