# SPDX-License-Identifier: AGPL-3.0-or-later
"""Starting change requests: reopening, budget, the queue, failure and retry."""

from decimal import Decimal

import pytest
from django.db import transaction

from dexterhouse.apps.projects.models import Artifact, ChangeRequest, Project, ProjectStatus
from dexterhouse.apps.projects.services import change_requests, lifecycle
from dexterhouse.apps.projects.services.transitions import transition
from dexterhouse.apps.workflows import services
from dexterhouse.apps.workflows.engine import common, steps
from dexterhouse.apps.workflows.models import Gate, PhaseRun, ProcessRun, StepRun, Task
from dexterhouse.common.errors import InvalidTransitionError
from tests.workflows.conftest import event_types, events

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_questions(settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}


def finish(project: Project, user) -> None:
    """Run steps and approve gates of the current run only, until that iteration ends."""
    project.refresh_from_db()
    run = project.current_run
    for _ in range(500):
        run.refresh_from_db()
        queued = StepRun.objects.filter(phase_run__process_run=run, status="queued")
        step = queued.order_by("created_at").first()
        gate = Gate.objects.filter(phase_run__process_run=run, status="open").first()
        if step is not None and step.project.status == "running":
            steps.run_step(step.id)
        elif gate is not None:
            services.decide(gate.id, user, decision="approve")
        else:
            break
    project.refresh_from_db()


def new_cr(project, user, **data) -> ChangeRequest:
    body = {"title": "Waiting list", "body": "Add a waiting list.", "budget": Decimal(4), **data}
    return change_requests.create_change_request(project, user, body)


@pytest.fixture
def completed(started, user) -> Project:
    project = started()
    finish(project, user)
    assert project.status == ProjectStatus.COMPLETED
    return project


def test_queue_on_completed_project_starts_iteration_one(completed, user):
    budget = completed.budget
    cr = change_requests.queue_change_request(new_cr(completed, user), user)
    completed.refresh_from_db()
    assert (cr.status, completed.status) == ("running", "running")
    run = completed.current_run
    assert (run.iteration, run.status, cr.process_run_id) == (1, "running", run.id)
    analysis = PhaseRun.objects.get(process_run=run, phase_id="analysis")
    assert analysis.status == "running"
    assert completed.budget == budget + 4
    assert completed.completed_at is None
    document = Artifact.objects.get(project=completed, kind="change_request")
    assert (document.name, document.version) == ("cr-1.md", 1)
    assert "Add a waiting list." in document.content
    reopened = events(completed, "project.reopened")[-1].payload
    assert (reopened["change_request"], reopened["iteration"]) == (str(cr.id), 1)
    assert events(completed, "project.budget_changed")[-1].payload["new"] == str(completed.budget)
    assert "change_request.started" in event_types(completed, "change_request.")
    assert event_types(completed, "budget.estimated")


def test_iteration_completes_the_cr_and_keeps_iteration_zero(completed, user):
    before = set(Task.objects.filter(project=completed).values_list("pk", "process_run"))
    cr = change_requests.queue_change_request(new_cr(completed, user), user)
    finish(completed, user)
    cr.refresh_from_db()
    assert (completed.status, cr.status) == ("completed", "completed")
    assert cr.completed_at is not None
    assert completed.completed_at is not None
    assert before <= set(Task.objects.filter(project=completed).values_list("pk", "process_run"))
    assert Task.objects.current(completed.id).count() == len(before)  # T-01.. again
    assert [r.status for r in ProcessRun.objects.filter(project=completed)] == ["completed"] * 2


def test_queued_crs_start_by_themselves_in_number_order(started, user):
    project = started()
    first, second = new_cr(project, user), new_cr(project, user, title="Export")
    change_requests.queue_change_request(second, user)
    change_requests.queue_change_request(first, user)
    assert {cr.status for cr in ChangeRequest.objects.all()} == {"queued"}
    finish(project, user)
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, second.status) == ("running", "queued")
    assert project.status == "running"
    finish(project, user)
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, second.status) == ("completed", "running")
    assert project.current_run.iteration == 2


def test_drafts_never_start_by_themselves(started, user):
    project = started()
    draft = new_cr(project, user)
    finish(project, user)
    draft.refresh_from_db()
    assert (project.status, draft.status) == ("completed", "draft")


def test_failed_iteration_fails_the_cr_and_retry_resumes_it(completed, user):
    cr = change_requests.queue_change_request(new_cr(completed, user), user)
    with transaction.atomic():
        _project, run = common.lock(completed.id)
        row = PhaseRun.objects.get(process_run=run, phase_id="analysis")
        row.process_run = run
        common.fail_phase(row, "loop_exhausted")
    cr.refresh_from_db()
    assert cr.status == "failed"
    assert "change_request.failed" in event_types(completed, "change_request.")
    lifecycle.retry_project(completed.id, user)
    cr.refresh_from_db()
    completed.refresh_from_db()
    assert (cr.status, completed.status) == ("running", "running")


def test_completed_to_running_only_through_a_change_request(completed, user):
    with pytest.raises(InvalidTransitionError):
        transition(completed, ProjectStatus.RUNNING)
    with pytest.raises(InvalidTransitionError):
        lifecycle.resume_project(completed.id, user)
    with pytest.raises(InvalidTransitionError):
        lifecycle.start_project(completed.id, user)


def test_zero_budget_cr_leaves_the_budget_alone(completed, user):
    budget = completed.budget
    change_requests.queue_change_request(new_cr(completed, user, budget=Decimal(0)), user)
    completed.refresh_from_db()
    assert completed.budget == budget
    assert not event_types(completed, "project.budget_changed")


def test_auto_start_refused_by_the_org_budget_leaves_the_cr_queued(started, user, monkeypatch):
    from dexterhouse.apps.observability.services import budget
    from dexterhouse.common.errors import BudgetExhaustedError

    project = started()
    cr = change_requests.queue_change_request(new_cr(project, user), user)

    def exhausted(_org):
        raise BudgetExhaustedError("the organization's monthly budget is exhausted")

    monkeypatch.setattr(budget, "ensure_org_can_start", exhausted)
    finish(project, user)
    cr.refresh_from_db()
    assert (project.status, cr.status) == ("completed", "queued")
    assert project.current_run.iteration == 0
