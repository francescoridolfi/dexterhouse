# SPDX-License-Identifier: AGPL-3.0-or-later
"""The iteration migrations keep single-run projects: iteration 0, tasks get their run."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("workflows", "0003_gate_reminders")]
AFTER = [("workflows", "0005_task_process_run")]


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.fixture(autouse=True)
def _back_to_latest():
    yield
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_existing_runs_become_iteration_zero_and_tasks_get_their_run(organization, user):
    apps = migrate(BEFORE)
    project = apps.get_model("projects", "Project").objects.create(
        organization_id=organization.id, name="Old", slug="old", brief="b",
        process_name="software-house-default", process_version="1.0.0", budget=1,
        created_by_id=user.id,
    )  # fmt: skip
    run = apps.get_model("workflows", "ProcessRun").objects.create(
        project=project, process_name="p", process_version="1", definition={}
    )
    phase = apps.get_model("workflows", "PhaseRun").objects.create(
        process_run=run, phase_id="implementation", position=0, room="open_space"
    )
    apps.get_model("workflows", "Task").objects.create(
        project=project, phase_run=phase, external_id="T-001", title="t", max_iterations=1,
        assigned_role="developer",
    )  # fmt: skip

    apps = migrate(AFTER)
    assert apps.get_model("workflows", "ProcessRun").objects.get().iteration == 0
    assert apps.get_model("workflows", "Task").objects.get().process_run_id == run.id
