# SPDX-License-Identifier: AGPL-3.0-or-later
"""Process iterations (ADR-0018): one run per iteration, the latest one is the current run."""

import pytest
from django.db import IntegrityError, transaction

from dexterhouse.apps.workflows.engine import common
from dexterhouse.apps.workflows.models import ProcessRun

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
