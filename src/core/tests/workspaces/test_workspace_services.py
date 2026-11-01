# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from datetime import timedelta

import pytest
import redis
from django.conf import settings
from django.utils import timezone

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import ProjectStatus
from dexterhouse.apps.workspaces import client as client_module
from dexterhouse.apps.workspaces import services
from dexterhouse.apps.workspaces.models import Workspace, WorkspaceStatus
from dexterhouse_schema.runner import Heartbeat, WorkspaceChanged

STACK = {
    "language": "python",
    "framework": "fastapi",
    "workspace_image": "dexterhouse/workspace:python",
    "test_command": "uv run pytest",
    "run_command": "uv run app",
    "services": ["postgres"],
}


def types(project) -> list[str]:
    return list(
        Event.objects.filter(project_id=project.id)
        .order_by("created_at", "id")
        .values_list("type", flat=True)
    )


@pytest.fixture
def stacked(project):
    project.stack = STACK
    project.save(update_fields=["stack"])
    return project


def test_request_sends_create_once(stacked, runner_client):
    workspace = services.request(stacked)
    assert workspace.status == "requested"
    assert services.pending(stacked.id)
    assert services.request(stacked).id == workspace.id
    assert [t for t, _ in runner_client.sent] == ["runner.workspace.create"]
    message = runner_client.sent[0][1]
    assert message.workspace_id == workspace.id
    assert message.stack["services"] == ["postgres"]
    assert message.limits.disk == "5G"
    assert types(stacked)[-1] == "workspace.requested"


def test_ready_callback_emits_created_and_ignores_stale(stacked, runner_client):
    workspace = services.request(stacked)
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="creating"), resume=False
    )
    services.apply_changed(
        WorkspaceChanged(
            workspace_id=workspace.id,
            status="ready",
            image="img",
            digest="sha256:1",
            container_id="c1",
            services=["postgres"],
        ),
        resume=False,
    )
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="creating"), resume=False
    )
    workspace.refresh_from_db()
    assert workspace.status == "ready"
    assert workspace.container_id == "c1"
    assert services.live(stacked.id) == workspace
    created = Event.objects.get(project_id=stacked.id, type="workspace.created")
    assert created.payload["digest"] == "sha256:1"
    assert created.payload["services"] == ["postgres"]
    assert services.apply_changed(WorkspaceChanged(workspace_id=stacked.id, status="ready")) is None


def test_three_failed_creations_escalate(
    stacked, runner_client, django_capture_on_commit_callbacks, monkeypatch
):
    escalated = []
    monkeypatch.setattr(services, "_escalate", lambda *a: escalated.append(a))
    workspace = services.request(stacked)
    for _ in range(3):
        with django_capture_on_commit_callbacks(execute=True):
            services.apply_changed(
                WorkspaceChanged(
                    workspace_id=workspace.id, status="error", error_detail="pull failed"
                )
            )
    workspace.refresh_from_db()
    assert workspace.status == "error"
    assert workspace.attempts == 3
    assert [t for t, _ in runner_client.sent].count("runner.workspace.create") == 3
    assert types(stacked).count("workspace.error") == 3
    assert escalated[0][1] == 3
    # escalation retry: start over
    services.retry(stacked)
    workspace.refresh_from_db()
    assert workspace.status == "requested"
    assert workspace.attempts == 0


def test_escalation_reason_is_known(stacked):
    from dexterhouse.apps.workflows.escalations import REASONS

    assert "workspace_error" in REASONS
    services._escalate(stacked.id, 3, "x")  # no running process: logged, not raised


def test_touch_resumes_idle_and_destroyed_callback(stacked, runner_client):
    workspace = services.request(stacked)
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="ready"), resume=False
    )
    Workspace.objects.filter(pk=workspace.pk).update(status=WorkspaceStatus.IDLE)
    workspace.refresh_from_db()
    services.touch(workspace)
    workspace.refresh_from_db()
    assert workspace.status == "ready"
    assert "workspace.resumed" in types(stacked)
    services.destroy(workspace, "archived")
    assert runner_client.sent[-1][0] == "runner.workspace.destroy"
    services.apply_changed(WorkspaceChanged(workspace_id=workspace.id, status="destroyed"))
    destroyed = Event.objects.get(project_id=stacked.id, type="workspace.destroyed")
    assert destroyed.payload == {"reason": "archived"}


def _ready(project, **fields):
    workspace = services.request(project)
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="ready"), resume=False
    )
    Workspace.objects.filter(pk=workspace.pk).update(**fields)
    workspace.refresh_from_db()
    return workspace


def test_cleanup_idles_and_destroys(stacked, runner_client):
    old = timezone.now() - timedelta(hours=settings.WORKSPACE_IDLE_DESTROY_H + 1)
    workspace = _ready(stacked, last_activity_at=timezone.now() - timedelta(minutes=20))
    stacked.status = ProjectStatus.RUNNING
    stacked.save(update_fields=["status"])
    assert services.cleanup() == {"idle": 1, "destroyed": 0}
    assert "workspace.idle" in types(stacked)
    Workspace.objects.filter(pk=workspace.pk).update(last_activity_at=old)
    assert services.cleanup()["destroyed"] == 0  # a running project keeps its code
    stacked.status = ProjectStatus.COMPLETED
    stacked.completed_at = old
    stacked.save(update_fields=["status", "completed_at"])
    assert services.cleanup()["destroyed"] == 1
    workspace.refresh_from_db()
    assert (workspace.status, workspace.destroy_reason) == ("destroying", "completed")


@pytest.mark.parametrize(("status", "reason"), [("archived", "archived"), ("failed", "inactive")])
def test_cleanup_reasons(stacked, runner_client, status, reason):
    old = timezone.now() - timedelta(hours=settings.WORKSPACE_IDLE_DESTROY_H + 1)
    workspace = _ready(stacked, last_activity_at=old, status=WorkspaceStatus.IDLE)
    stacked.status = status
    stacked.save(update_fields=["status"])
    services.cleanup()
    workspace.refresh_from_db()
    assert workspace.destroy_reason == reason


def test_heartbeat_marks_the_runner_alive_and_destroys_orphans(stacked, runner_client):
    workspace = _ready(stacked)
    orphan = "0190f0f0-0000-7000-8000-000000000001"
    services.apply_heartbeat(
        Heartbeat(
            runner_id="r-test",
            version="0.1.0",
            active_workspaces=2,
            workspaces=[workspace.id, orphan],
        )
    )
    stored = redis.Redis.from_url(settings.REDIS_URL).get("runner:heartbeat:r-test")
    assert json.loads(stored)["active_workspaces"] == 2
    assert "r-test" in client_module.runner_heartbeats()
    destroys = [m for t, m in runner_client.sent if t == "runner.workspace.destroy"]
    assert [str(m.workspace_id) for m in destroys] == [orphan]
    redis.Redis.from_url(settings.REDIS_URL).delete("runner:heartbeat:r-test")


def test_metrics_export_workspaces_and_runner(stacked, runner_client, client):
    _ready(stacked)
    services.apply_heartbeat(
        Heartbeat(
            runner_id="r-metrics",
            version="0.1.0",
            active_workspaces=1,
            metrics={"exec_total": 7, "egress_denied_total": 2},
        )
    )
    text = client.get("/metrics").content.decode()
    redis.Redis.from_url(settings.REDIS_URL).delete("runner:heartbeat:r-metrics")
    assert "dh_workspaces_active 1.0" in text
    assert 'dh_runner_exec_total{runner="r-metrics"} 7.0' in text
    assert 'dh_runner_egress_denied_total{runner="r-metrics"} 2.0' in text
    assert "dh_runner_up 1.0" in text
