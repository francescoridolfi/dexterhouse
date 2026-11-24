# SPDX-License-Identifier: AGPL-3.0-or-later
"""E-13 end to end with the fake turn runner: brief -> release-1 -> CR-1 -> release-2.

The runner is the inline `LocalRunnerClient`, recording what the core sends: the snapshot
after each iteration and the restore of the destroyed workspace for the change request.
"""

from decimal import Decimal

import pytest

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import ChangeRequest
from dexterhouse.apps.projects.services import change_requests, context, lifecycle
from dexterhouse.apps.workflows.models import ProcessRun
from dexterhouse.apps.workspaces import client as client_module
from dexterhouse.apps.workspaces import services
from dexterhouse.apps.workspaces.client import LocalRunnerClient
from dexterhouse.common import crypto
from tests.workflows.conftest import finish

pytestmark = [pytest.mark.slow, pytest.mark.django_db(transaction=True)]
STACK = {
    "language": "python",
    "framework": "none",
    "workspace_image": "dexterhouse/workspace:python",
}


class RecordingRunner(LocalRunnerClient):
    def __init__(self) -> None:
        self.messages: list[tuple[str, object]] = []

    def call(self, task, message, timeout_s=None):
        self.messages.append((task, message))
        return super().call(task, message, timeout_s)

    def send(self, task, message):
        self.messages.append((task, message))
        return super().send(task, message)

    def of(self, task: str) -> list:
        return [m for t, m in self.messages if t == task]


@pytest.fixture
def runner(monkeypatch, settings, tmp_path):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}
    settings.WORKFLOWS_REPO_CHECKER = "tests.workflows.test_e2e_change_request.repo_ok"
    settings.CONTEXT_DIR = tmp_path / "context"
    recorder = RecordingRunner()
    monkeypatch.setattr(client_module, "import_string", lambda path: lambda: recorder)
    return recorder


def repo_ok(url: str, token: str | None) -> None:
    return None


def _delivered(project) -> list[dict]:
    rows = Event.objects.filter(project_id=project.id, type="release.delivered")
    return [e.payload for e in rows.order_by("created_at", "id")]


def test_brief_release_one_change_request_release_two(make_project, user, runner):
    project = make_project(execution_mode="supervised")
    project.stack = STACK
    project.remote_repo_url = "https://github.com/acme/gymbook"
    project.remote_token = crypto.encrypt("ghp_e2e_token")
    project.save()
    context.add_document(project, user, filename="analysis.md", content=b"# Limits\n\n200 ms.")

    lifecycle.start_project(project.id, user)
    finish(project, user)
    assert project.status == "completed"
    assert [d["branch"] for d in _delivered(project)] == ["dexterhouse/release-1"]
    assert len(runner.of("runner.system.snapshot")) == 1

    workspace = services.for_project(project.id)
    services.destroy(workspace, "completed")  # the 24 h cleanup ran before the CR
    workspace.refresh_from_db()
    assert workspace.status == "destroyed"

    cr = change_requests.create_change_request(
        project,
        user,
        {"title": "Waiting list", "body": "Add a waiting list.", "budget": Decimal(3)},
    )
    context.add_document(
        project, user, filename="waitlist.md", content=b"FIFO.", change_request_id=cr.id
    )
    change_requests.queue_change_request(cr, user)
    finish(project, user)

    cr.refresh_from_db()
    assert (project.status, cr.status) == ("completed", "completed")
    assert [r.iteration for r in ProcessRun.objects.filter(project=project)] == [0, 1]
    assert [d["branch"] for d in _delivered(project)] == [
        "dexterhouse/release-1",
        "dexterhouse/release-2",
    ]
    creates = runner.of("runner.workspace.create")
    assert creates[0].restore is None
    assert creates[-1].restore.source == "snapshot"
    prs = [m.pr.title for m in runner.of("runner.system.deliver")]
    assert prs[-1] == "CR-1: Waiting list (GymBook release 2)"
    assert len(runner.of("runner.system.snapshot")) == 2
    assert ChangeRequest.objects.get(pk=cr.id).process_run.iteration == 1

    lifecycle.archive_project(project.id, user)
    assert runner.of("runner.system.snapshot_drop")[0].project_id == project.id
