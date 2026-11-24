# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inputs of a change request iteration: the CR, the last release, what exists already."""

from decimal import Decimal

import pytest

from dexterhouse.apps.projects.services import change_requests
from dexterhouse.apps.workflows import services
from dexterhouse.apps.workflows.engine import steps
from dexterhouse.apps.workflows.models import Gate, StepRun
from dexterhouse.apps.workflows.runners.inputs import build_inputs
from tests.workflows.conftest import finish

pytestmark = pytest.mark.django_db


def reopen(project, user, number: int = 1):
    for n in range(number):
        body = {"title": f"Change {n + 1}", "body": f"Do change {n + 1}.", "budget": Decimal(1)}
        cr = change_requests.create_change_request(project, user, body)
    return change_requests.queue_change_request(cr, user)


def inputs_of(project, role: str):
    step = StepRun.objects.filter(
        phase_run__process_run=project.current_run, role=role, status="queued"
    ).first()
    assert step is not None, role
    return build_inputs(steps.build_request(step, attempt=1), step)


def test_analyst_reads_the_cr_first_and_what_was_delivered(completed, user):
    cr = reopen(completed, user)
    inputs = inputs_of(completed, "analyst")
    kinds = [a.kind for a in inputs.artifacts]
    assert kinds[:2] == ["change_request", "release_notes"]
    assert {"requirements", "user_stories", "architecture", "stack"} <= set(kinds)
    assert len(kinds) == len({(a.kind, a.name) for a in inputs.artifacts})
    (document,) = [a for a in inputs.artifacts if a.kind == "change_request"]
    assert document.name == f"cr-{cr.number}.md"
    assert "Do change 1." in document.content
    assert "CR-1" in inputs.step_description
    assert "added, changed or removed" in inputs.step_description


def test_only_the_current_cr_is_read(completed, user):
    reopen(completed, user)
    finish(completed, user)  # CR-1 delivered: CR-2 must not see cr-1.md
    cr = change_requests.queue_change_request(
        change_requests.create_change_request(
            completed, user, {"title": "Export", "body": "CSV export.", "budget": Decimal(0)}
        ),
        user,
    )
    artifacts = inputs_of(completed, "analyst").artifacts
    names = [a.name for a in artifacts if a.kind == "change_request"]
    assert names == [f"cr-{cr.number}.md"]


def test_brief_iteration_inputs_are_unchanged(started):
    project = started()
    inputs = inputs_of(project, "analyst")
    assert "change_request" not in {a.kind for a in inputs.artifacts}
    assert "CR-" not in inputs.step_description


def test_planning_of_an_iteration_has_no_scaffold_task(completed, user):
    reopen(completed, user)
    run = completed.current_run
    for _ in range(50):  # run until the project manager's planning step is queued
        step = StepRun.objects.filter(phase_run__process_run=run, status="queued").first()
        if step is None or step.role == "project_manager":
            break
        steps.run_step(step.id)
        gate = Gate.objects.filter(phase_run__process_run=run, status="open").first()
        if gate is not None:
            services.decide(gate.id, user, decision="approve")
    description = inputs_of(completed, "project_manager").step_description
    assert "no scaffold task" in description


def test_documents_attached_to_the_cr_come_right_after_it(completed, user, settings, tmp_path):
    from dexterhouse.apps.projects.services import context

    settings.CONTEXT_DIR = tmp_path / "context"
    general = context.add_document(completed, user, filename="domain.md", content=b"Gyms.")
    body = {"title": "Waiting list", "body": "Add one.", "budget": Decimal(0)}
    cr = change_requests.create_change_request(completed, user, body)
    attached = context.add_document(
        completed, user, filename="waitlist.md", content=b"FIFO.", change_request_id=cr.id
    )
    for doc in (general, attached):
        context.process_document(doc.id)
    change_requests.queue_change_request(cr, user)
    names = [a.name for a in inputs_of(completed, "analyst").artifacts]
    assert names[:2] == [f"cr-{cr.number}.md", "context/waitlist.md"]
    assert names.index("context/domain.md") > names.index("context/waitlist.md")
