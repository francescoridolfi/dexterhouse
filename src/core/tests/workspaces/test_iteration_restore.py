# SPDX-License-Identifier: AGPL-3.0-or-later
"""Core side of ADR-0018: snapshot at the end of an iteration, restore for a change request."""

import pytest

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.workspaces import services
from dexterhouse.apps.workspaces.models import Workspace, WorkspaceStatus
from dexterhouse.common import crypto
from dexterhouse_schema.runner import ToolResult, WorkspaceChanged

pytestmark = pytest.mark.django_db
STACK = {
    "language": "python",
    "framework": "none",
    "workspace_image": "dexterhouse/workspace:python",
}


@pytest.fixture
def stacked(project):
    project.stack = STACK
    project.save(update_fields=["stack"])
    return project


def _workspace(project, status):
    return Workspace.objects.create(project=project, status=status, stack=STACK)


def _creates(runner_client):
    return [m for t, m in runner_client.sent if t == "runner.workspace.create"]


def test_destroyed_workspace_is_restored_from_the_snapshot(stacked, runner_client):
    _workspace(stacked, WorkspaceStatus.DESTROYED)
    services.prepare_for_iteration(stacked)
    workspace = services.request(stacked)
    (create,) = _creates(runner_client)
    assert create.restore.source == "snapshot"
    assert create.workspace_id == workspace.id
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="ready", restored_commit="abc123"),
        resume=False,
    )
    workspace.refresh_from_db()
    assert workspace.restored_commit == "abc123"
    created = Event.objects.filter(project_id=stacked.id, type="workspace.created").get()
    assert created.payload["restored_commit"] == "abc123"


def test_live_workspace_is_reused_and_first_workspace_has_no_restore(stacked, runner_client):
    live = _workspace(stacked, WorkspaceStatus.IDLE)
    services.prepare_for_iteration(stacked)
    assert services.request(stacked).id == live.id
    assert _creates(runner_client) == []
    live.delete()
    services.prepare_for_iteration(stacked)  # never had a workspace: nothing to restore
    services.request(stacked)
    assert _creates(runner_client)[0].restore is None


def test_failed_snapshot_restore_falls_back_to_the_delivered_branch(stacked, runner_client):
    stacked.remote_repo_url = "https://github.com/acme/gymbook"
    stacked.remote_token = crypto.encrypt("ghp_x")
    stacked.save(update_fields=["remote_repo_url", "remote_token"])
    Event.objects.create(
        organization_id=stacked.organization_id,
        project_id=stacked.id,
        type="release.delivered",
        schema_version=1,
        actor_type="system",
        payload={"branch": "dexterhouse/release-1", "commit": "c1", "mode": "pull_request"},
        correlation_id=stacked.id,
        created_at=stacked.created_at,
    )
    _workspace(stacked, WorkspaceStatus.DESTROYED)
    services.prepare_for_iteration(stacked)
    workspace = services.request(stacked)
    services.apply_changed(
        WorkspaceChanged(
            workspace_id=workspace.id,
            status="error",
            error_detail="restore from the snapshot failed: the project has no snapshot",
        ),
        resume=False,
    )
    first, second = _creates(runner_client)
    assert first.restore.source == "snapshot"
    assert second.restore.source == "remote"
    assert second.restore.remote_url == "https://github.com/acme/gymbook"
    assert second.restore.branch == "dexterhouse/release-1"
    assert second.restore.token_ref is not None
    assert "ghp_x" not in second.model_dump_json()


def test_without_a_remote_a_failed_restore_escalates(stacked, runner_client):
    _workspace(stacked, WorkspaceStatus.DESTROYED)
    services.prepare_for_iteration(stacked)
    workspace = services.request(stacked)
    detail = "restore from the snapshot failed: the project has no snapshot"
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="error", error_detail=detail),
        resume=False,
    )
    workspace.refresh_from_db()
    assert workspace.status == WorkspaceStatus.ERROR
    assert len(_creates(runner_client)) == 1


def test_snapshot_of_a_live_workspace_and_drop(stacked, runner_client):
    runner_client.results["runner.system.snapshot"] = ToolResult(
        ok=True, data={"commit": "f00d", "size": 1234}
    )
    assert services.snapshot(stacked.id) is None  # no workspace yet
    workspace = _workspace(stacked, WorkspaceStatus.READY)
    assert services.snapshot(stacked.id) == "f00d"
    workspace.refresh_from_db()
    assert workspace.snapshot_commit == "f00d"
    assert workspace.snapshot_at is not None
    ((task, message),) = runner_client.calls
    assert task == "runner.system.snapshot"
    assert (message.workspace_id, message.project_id) == (workspace.id, stacked.id)
    services.drop_snapshot(stacked.id)
    assert runner_client.tasks()[-1] == "runner.system.snapshot_drop"


def test_a_failed_snapshot_is_logged_not_raised(stacked, runner_client):
    runner_client.results["runner.system.snapshot"] = ToolResult.failure("invalid", "nope")
    _workspace(stacked, WorkspaceStatus.READY)
    assert services.snapshot(stacked.id) is None
