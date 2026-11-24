# SPDX-License-Identifier: AGPL-3.0-or-later
"""A change request is delivered as the next release, named after the CR."""

import pytest
from django.utils import timezone

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import ChangeRequest
from dexterhouse.apps.workflows.models import PhaseRun, ProcessRun
from dexterhouse.apps.workspaces import delivery, services
from dexterhouse.common import crypto
from dexterhouse_schema.runner import ToolResult, WorkspaceChanged

pytestmark = pytest.mark.django_db


@pytest.fixture
def reopened(project, user, runner_client):
    """CR-1 running on a project already delivered once (release-1), with a live workspace."""
    project.remote_token = crypto.encrypt("ghp_secret_value")
    project.remote_repo_url = "https://github.com/acme/gymbook"
    project.save()
    Event.objects.create(
        organization_id=project.organization_id, project_id=project.id, type="release.delivered",
        schema_version=1, actor_type="system", actor_name="engine", payload={},
        correlation_id=project.id, created_at=timezone.now(),
    )  # fmt: skip
    run = ProcessRun.objects.create(
        project=project, iteration=1, process_name="p", process_version="1", definition={}
    )
    row = PhaseRun.objects.create(process_run=run, phase_id="release", position=0, room="x")
    ChangeRequest.objects.create(
        project=project, number=1, title="Waiting list", body="b", created_by=user,
        status="running", process_run=run,
    )  # fmt: skip
    workspace = services.request(project)
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="ready"), resume=False
    )
    runner_client.results["runner.system.deliver"] = ToolResult(ok=True, data={"commit": "c"})
    return row


def test_cr_is_delivered_as_release_two_named_after_it(project, reopened, runner_client):
    assert delivery.deliver(project.id, reopened.id) == "delivered"
    message = runner_client.calls[-1][1]
    assert message.branch_name == "dexterhouse/release-2"
    assert message.pr.title == "CR-1: Waiting list (GymBook release 2)"
    assert message.pr.body.startswith("CR-1: Waiting list\n")
