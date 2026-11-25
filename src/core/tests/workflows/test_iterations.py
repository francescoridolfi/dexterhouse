# SPDX-License-Identifier: AGPL-3.0-or-later
"""Process iterations (ADR-0018): one run per iteration, the latest one is the current run."""

import pytest
from django.db import IntegrityError, transaction

from dexterhouse.apps.workflows.engine import common, loop
from dexterhouse.apps.workflows.models import PhaseRun, ProcessRun, Task

pytestmark = pytest.mark.django_db


def next_run(project, iteration: int) -> ProcessRun:
    return ProcessRun.objects.create(
        project=project, iteration=iteration, process_name="p", process_version="1", definition={}
    )


def test_started_project_runs_iteration_zero(started):
    project = started()
    run = project.current_run
    assert run is not None
    assert run.iteration == 0


def test_lock_and_current_run_return_the_latest_iteration(started):
    project = started()
    first = project.current_run
    second = next_run(project, 1)
    with transaction.atomic():
        locked_project, run = common.lock(project.id)
    assert run.pk == second.pk
    assert run.project is locked_project
    assert project.current_run.pk == second.pk
    assert set(project.process_runs.values_list("pk", flat=True)) == {first.pk, second.pk}


def test_draft_project_has_no_current_run(project):
    assert project.current_run is None
    with transaction.atomic():
        assert common.lock(project.id)[1] is None


def test_iteration_is_unique_per_project(started):
    project = started()
    with pytest.raises(IntegrityError), transaction.atomic():
        next_run(project, 0)


def test_phase_list_api_shows_the_current_iteration(started, client):
    project = started()
    next_run(project, 1)  # no phase runs yet
    url = f"/api/v1/projects/{project.id}/phases"
    assert client.get(url).json()["results"] == []
    assert len(client.get(url, {"iteration": 0}).json()["results"]) > 0


def board_task(row, external_id: str = "T-001") -> Task:
    return Task.objects.create(
        project=row.process_run.project,
        process_run=row.process_run,
        phase_run=row,
        external_id=external_id,
        title="Booking",
        max_iterations=1,
        assigned_role="developer",
    )


def test_each_iteration_has_its_own_task_board(started):
    project = started()
    first = PhaseRun.objects.filter(process_run=project.current_run).first()
    board_task(first)
    run = next_run(project, 1)
    second = PhaseRun.objects.create(process_run=run, phase_id="implementation", position=0)
    board_task(second)  # T-001 again, on the new run
    assert loop.next_external_id(project) == "T-02"
    with pytest.raises(IntegrityError), transaction.atomic():
        board_task(second)
    assert list(Task.objects.current(project.id).values_list("process_run", flat=True)) == [run.pk]


def test_task_list_api_shows_the_current_iteration(started, client):
    project = started()
    board_task(PhaseRun.objects.filter(process_run=project.current_run).first())
    run = next_run(project, 1)
    url = f"/api/v1/projects/{project.id}/tasks"
    assert client.get(url).json()["results"] == []
    assert len(client.get(url, {"iteration": 0}).json()["results"]) == 1
    board_task(PhaseRun.objects.create(process_run=run, phase_id="x", position=0))
    assert len(client.get(url).json()["results"]) == 1
