# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import timedelta
from unittest import mock

import pytest
from django.test import Client
from django.utils import timezone

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.workspaces import delivery, services
from dexterhouse.apps.workspaces.grants import create_grant, purge
from dexterhouse.apps.workspaces.models import SecretGrant
from dexterhouse.common import crypto
from dexterhouse_schema.runner import ToolResult, WorkspaceChanged

KEY = {"HTTP_X_RUNNER_KEY": "test-runner-key"}


@pytest.fixture
def tokened(project):
    project.remote_token = crypto.encrypt("ghp_secret_value")
    project.remote_repo_url = "https://github.com/acme/gymbook"
    project.stack = {"workspace_image": "dexterhouse/workspace:python"}
    project.save()
    return project


def test_grant_is_one_time(tokened):
    grant = create_grant(tokened)
    http = Client()
    assert http.get(f"/internal/secrets/{grant.id}").status_code == 401
    assert http.get(f"/internal/secrets/{grant.id}", HTTP_X_RUNNER_KEY="wrong").status_code == 401
    first = http.get(f"/internal/secrets/{grant.id}", **KEY)
    assert first.status_code == 200
    assert first.json() == {"value": "ghp_secret_value"}
    assert first["Cache-Control"].startswith("max-age=0")
    assert http.get(f"/internal/secrets/{grant.id}", **KEY).status_code == 404
    assert http.post(f"/internal/secrets/{grant.id}", **KEY).status_code == 405


def test_expired_grant_and_purge(tokened):
    grant = create_grant(tokened)
    SecretGrant.objects.filter(pk=grant.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert Client().get(f"/internal/secrets/{grant.id}", **KEY).status_code == 404
    create_grant(tokened)
    assert purge(timezone.now() + timedelta(minutes=2)) == 2
    assert not SecretGrant.objects.exists()


def _live(project):
    workspace = services.request(project)
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="ready"), resume=False
    )
    return workspace


def test_deliver_pull_request(tokened, runner_client):
    _live(tokened)
    runner_client.results["runner.system.deliver"] = ToolResult(
        ok=True,
        data={
            "commit": "abc",
            "branch": "dexterhouse/release-1",
            "pr_url": "https://github.com/acme/gymbook/pull/1",
        },
    )
    assert delivery.deliver(tokened.id, tokened.id) == "delivered"
    message = runner_client.calls[-1][1]
    assert message.branch_name == "dexterhouse/release-1"
    assert message.pr.title == "GymBook: release 1"
    assert SecretGrant.objects.get(pk=message.token_ref).project_id == tokened.id
    assert "ghp_secret_value" not in message.model_dump_json()
    event = Event.objects.get(project_id=tokened.id, type="release.delivered")
    assert event.payload["pr_url"].endswith("/pull/1")
    assert delivery.release_number(tokened) == 2


def test_deliver_failure_and_skip(tokened, runner_client):
    _live(tokened)
    runner_client.results["runner.system.deliver"] = ToolResult.failure("protected_branch", "GH006")
    tokened.delivery_mode = "push_main"
    tokened.save(update_fields=["delivery_mode"])
    assert delivery.deliver(tokened.id, tokened.id) == "failed"
    assert runner_client.calls[-1][1].branch_name is None
    failed = Event.objects.get(project_id=tokened.id, type="release.failed")
    assert failed.payload["error_code"] == "protected_branch"
    runner_client.results["runner.system.deliver"] = ToolResult.failure("internal", "boom")
    delivery.deliver(tokened.id, tokened.id)
    codes = [e.payload["error_code"] for e in Event.objects.filter(type="release.failed")]
    assert codes == ["protected_branch", "network"]
    tokened.remote_repo_url = None
    tokened.save(update_fields=["remote_repo_url"])
    assert delivery.deliver(tokened.id, tokened.id) == "skipped"


def test_deliver_without_workspace(tokened, runner_client):
    assert delivery.deliver(tokened.id, tokened.id) == "failed"
    assert not runner_client.calls


def test_celery_client_without_heartbeat_fails_fast():
    from dexterhouse.apps.workspaces.client import CeleryRunnerClient
    from dexterhouse_schema.runner import WorkspaceStatusQuery

    with mock.patch("dexterhouse.apps.workspaces.client.runner_heartbeats", return_value={}):
        result = CeleryRunnerClient().call(
            "runner.workspace.status",
            WorkspaceStatusQuery(workspace_id="0190f0f0-0000-7000-8000-000000000001"),
        )
    assert result.error.code == "workspace_not_ready"


def test_celery_client_round_trip_and_timeout():
    from celery.exceptions import TimeoutError as CeleryTimeout

    from dexterhouse.apps.workspaces.client import CeleryRunnerClient
    from dexterhouse_schema.runner import WorkspaceStatusQuery

    message = WorkspaceStatusQuery(workspace_id="0190f0f0-0000-7000-8000-000000000001")
    with (
        mock.patch("dexterhouse.apps.workspaces.client.runner_heartbeats", return_value={"r": {}}),
        mock.patch("dexterhouse.apps.workspaces.client.celery_app.send_task") as send,
    ):
        send.return_value.get.return_value = {"schema": 1, "ok": True, "data": {"status": "ready"}}
        assert CeleryRunnerClient().call("runner.workspace.status", message).data == {
            "status": "ready"
        }
        assert send.call_args[1]["queue"] == "runner"
        assert send.return_value.get.call_args[1]["timeout"] == 25
        send.return_value.get.side_effect = CeleryTimeout()
        assert CeleryRunnerClient().call("runner.workspace.status", message).error.code == "timeout"
        send.side_effect = OSError("broker down")
        assert (
            CeleryRunnerClient().call("runner.workspace.status", message).error.code == "internal"
        )


def test_local_client_answers_without_a_runner():
    from dexterhouse.apps.workspaces.client import LocalRunnerClient
    from dexterhouse_schema.runner import CommitLog, Tree

    local = LocalRunnerClient()
    ws = "0190f0f0-0000-7000-8000-000000000001"
    assert local.call("runner.system.commit_log", CommitLog(workspace_id=ws)).data == {
        "commits": []
    }
    assert (
        local.call("runner.system.tree", Tree(workspace_id=ws)).error.code == "workspace_not_ready"
    )
